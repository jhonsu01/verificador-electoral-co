#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registraduria_tracker.py
========================
Herramienta deterministica de seguimiento y auditoria de los boletines de
resultados de las Elecciones Presidenciales de Colombia 2026
(portal: https://resultados.registraduria.gov.co).

OBJETIVO
--------
Capturar, de forma reproducible y con cadena de custodia (SHA-256 + timestamp),
cada avance/boletin publicado por la Registraduria, para:
  1. Llevar el registro de "a que hora se informo cada cosa" (linea temporal
     de mesas escrutadas por scope territorial).
  2. Conservar snapshots inmutables que luego puedan auditarse contra los
     hashes de los formularios E-14 publicados dias despues.

REALIDAD DE LA FUENTE (verificada el 2026-06-21)
------------------------------------------------
  - El portal sirve JSON estatico (S3 + CloudFront). NO hay PDFs server-side.
  - electionSiglas = "PR" (Presidente 2026), una sola eleccion.
  - Endpoints:
      Resultados+historico por scope : /json/ACT/PR/{scope}.json
      Deteccion de nuevos avances    : /json/notification.json   (71 bytes)
      Nomenclator (arbol territorial): /json/nomenclator.json
      Config web                     : /json/web/config.json
  - Granularidad maxima disponible   : MUNICIPIO (1 nacional + 34 deptos + 1189
                                       municipios). NO hay datos por mesa aqui.
  - Cada ACT trae:
      numact  -> numero de boletin/avance
      mdhm    -> timestamp "MMDDHHmm" (mes-dia-hora-min, hora Colombia UTC-5)
      totales.act.{metota,mesesc,meserr,...} -> mesas totales/escrutadas/error
      historico[] -> serie temporal completa de avances de ese scope

USO
---
  python registraduria_tracker.py scopes      # genera config/scopes.json desde el nomenclator
  python registraduria_tracker.py status      # consulta notification.json (version + mdhm actual)
  python registraduria_tracker.py snapshot     # captura UN snapshot de todos los scopes
  python registraduria_tracker.py snapshot --level 1   # solo nacional
  python registraduria_tracker.py snapshot --level 2   # nacional + departamentos
  python registraduria_tracker.py track --interval 30  # bucle: captura en cada nuevo avance
  python registraduria_tracker.py timeseries   # exporta CSV de mesas-vs-hora por scope

DISENO
------
  - Idempotente: re-ejecutar no duplica; cada snapshot se identifica por numact.
  - Append-only manifest (data/manifest.csv) = bitacora de auditoria inmutable.
  - Solo stdlib (urllib). Reintentos con backoff ante 403/timeout (CloudFront
    limita el ratio; un UA de navegador y reintentos lo resuelven).
"""

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #
BASE_HOST = "https://resultados.registraduria.gov.co"
# Prefijo de datos segun la vuelta:
#   2a vuelta (activa) -> "/v2"   |   1a vuelta -> ""  (raiz)
# El frontend de 2a vuelta usa VITE_SERVER_URL="/v2", asi que los datos viven
# en /v2/json/... (los de /json/... son 1a vuelta y NO se actualizan).
ROUND_PREFIX = "/v2"
ELECTION = "PR"  # siglas de la eleccion (Presidente 2026)


def set_round(round_num: int) -> None:
    """1 = primera vuelta (raiz), 2 = segunda vuelta (/v2)."""
    global ROUND_PREFIX
    ROUND_PREFIX = "" if round_num == 1 else "/v2"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Rutas locales (relativas a la raiz del proyecto)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
TS_DIR = os.path.join(DATA_DIR, "timeseries")
CONFIG_DIR = os.path.join(ROOT, "config")
SCOPES_FILE = os.path.join(CONFIG_DIR, "scopes.json")
MANIFEST = os.path.join(DATA_DIR, "manifest.csv")

# Parametros de red
MAX_WORKERS = 6          # paralelismo cortes (amable con CloudFront)
MAX_RETRIES = 4
TIMEOUT = 30


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, TS_DIR, CONFIG_DIR):
        os.makedirs(d, exist_ok=True)


def http_get(path: str, retries: int = MAX_RETRIES, bust: str | None = None) -> bytes:
    """GET con UA de navegador, prefijo de vuelta, cache-busting y reintentos.

    `bust` (normalmente la version de notification.json) se anexa como query
    para evitar copias rancias de CloudFront, igual que hace el frontend.
    """
    if path.startswith("http"):
        url = path
    else:
        url = BASE_HOST + ROUND_PREFIX + path
    if bust is not None:
        url += ("&" if "?" in url else "?") + "v=" + str(bust)
    headers = {"User-Agent": USER_AGENT, "Cache-Control": "no-cache",
               "Pragma": "no-cache"}
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            # 404 no se reintenta: el scope no existe
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                raise
            time.sleep(min(2 ** attempt, 8) + 0.25 * attempt)
    raise last_err  # type: ignore[misc]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mdhm_to_iso(mdhm: str, year: str = "2026") -> str:
    """Convierte 'MMDDHHmm' (hora Colombia UTC-5) a ISO 8601 con offset."""
    if not mdhm or len(mdhm) != 8 or not mdhm.isdigit():
        return ""
    mm, dd, hh, mi = mdhm[0:2], mdhm[2:4], mdhm[4:6], mdhm[6:8]
    return f"{year}-{mm}-{dd}T{hh}:{mi}:00-05:00"


# --------------------------------------------------------------------------- #
# Comando: scopes  (construye la lista de scopes desde el nomenclator)
# --------------------------------------------------------------------------- #
def build_scopes() -> list:
    """Descarga el nomenclator y genera la lista plana de scopes territoriales."""
    _ensure_dirs()
    raw = http_get("/json/nomenclator.json")
    nom = json.loads(raw)
    level_names = {l["l"]: l["n"] for l in nom.get("levels", [])}
    ambitos = nom["amb"][0]["ambitos"]
    scopes = []
    for a in ambitos:
        scopes.append({
            "code": a["co"],
            "name": a["n"],
            "level": a["l"],
            "level_name": level_names.get(a["l"], str(a["l"])),
        })
    scopes.sort(key=lambda s: (s["level"], s["code"]))
    with open(SCOPES_FILE, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": _utc_now(), "election": ELECTION,
                   "count": len(scopes), "scopes": scopes}, fh,
                  ensure_ascii=False, indent=2)
    by_level = {}
    for s in scopes:
        by_level[s["level_name"]] = by_level.get(s["level_name"], 0) + 1
    print(f"[scopes] {len(scopes)} scopes -> {SCOPES_FILE}")
    for lvl, n in by_level.items():
        print(f"         {lvl}: {n}")
    return scopes


def load_scopes(max_level: int | None = None) -> list:
    if not os.path.exists(SCOPES_FILE):
        build_scopes()
    with open(SCOPES_FILE, encoding="utf-8") as fh:
        scopes = json.load(fh)["scopes"]
    if max_level is not None:
        scopes = [s for s in scopes if s["level"] <= max_level]
    return scopes


# --------------------------------------------------------------------------- #
# Comando: status  (lee notification.json)
# --------------------------------------------------------------------------- #
def get_status() -> dict:
    raw = http_get("/json/notification.json")
    notif = json.loads(raw)
    pr = notif.get("dataDefinitions", {}).get(ELECTION, {})
    return {"version": pr.get("version"), "mdhm": pr.get("mdhm"),
            "iso": mdhm_to_iso(pr.get("mdhm", ""))}


def cmd_status(_args) -> None:
    st = get_status()
    print(f"[status] version={st['version']}  mdhm={st['mdhm']}  ({st['iso']})")


# --------------------------------------------------------------------------- #
# Comando: snapshot  (captura inmutable de todos los scopes)
# --------------------------------------------------------------------------- #
def _append_manifest(rows: list) -> None:
    new_file = not os.path.exists(MANIFEST)
    with open(MANIFEST, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["captured_at_utc", "election", "scope_code", "scope_name",
                        "level", "numact", "mdhm", "mdhm_iso", "metota", "mesesc",
                        "meserr", "sha256", "bytes", "raw_path"])
        w.writerows(rows)


def _fetch_one(scope: dict, bust: str | None = None) -> dict | None:
    """Descarga el ACT de un scope; devuelve metadata o None si 404."""
    path = f"/json/ACT/{ELECTION}/{scope['code']}.json"
    try:
        raw = http_get(path, bust=bust)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    d = json.loads(raw)
    tot = d.get("totales", {}).get("act", {})
    return {
        "scope": scope,
        "raw": raw,
        "numact": d.get("numact", ""),
        "mdhm": d.get("mdhm", ""),
        "metota": tot.get("metota", ""),
        "mesesc": tot.get("mesesc", ""),
        "meserr": tot.get("meserr", ""),
        "sha256": sha256_hex(raw),
    }


def take_snapshot(max_level: int | None = None) -> dict:
    """Captura un snapshot completo. Idempotente por (numact, scope)."""
    _ensure_dirs()
    scopes = load_scopes(max_level)
    status = get_status()
    numact = str(status["version"])
    snap_dir = os.path.join(RAW_DIR, f"avance_{numact.zfill(4)}")
    os.makedirs(snap_dir, exist_ok=True)

    print(f"[snapshot] avance={numact} mdhm={status['mdhm']} "
          f"scopes={len(scopes)} (nivel<= {max_level or 'todos'})")

    rows, saved, skipped, missing = [], 0, 0, 0
    captured_at = _utc_now()

    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_one, s, numact): s for s in scopes}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            s = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! error {s['code']} ({s['name']}): {exc}")
                continue
            if res is None:
                missing += 1
                continue
            raw_path = os.path.join(snap_dir, f"ACT_{ELECTION}_{s['code']}.json")
            # Idempotencia: si ya existe identico, no reescribir
            if os.path.exists(raw_path) and \
               sha256_hex(open(raw_path, "rb").read()) == res["sha256"]:
                skipped += 1
            else:
                with open(raw_path, "wb") as fh:
                    fh.write(res["raw"])
                saved += 1
            rows.append([
                captured_at, ELECTION, s["code"], s["name"], s["level"],
                res["numact"], res["mdhm"], mdhm_to_iso(res["mdhm"]),
                res["metota"], res["mesesc"], res["meserr"],
                res["sha256"], len(res["raw"]),
                os.path.relpath(raw_path, ROOT).replace("\\", "/"),
            ])
            if i % 200 == 0:
                print(f"  ... {i}/{len(scopes)}")

    _append_manifest(rows)
    summary = {"numact": numact, "mdhm": status["mdhm"], "scopes": len(scopes),
               "saved": saved, "skipped": skipped, "missing": missing,
               "snap_dir": os.path.relpath(snap_dir, ROOT)}
    print(f"[snapshot] OK avance={numact}: guardados={saved} "
          f"sin_cambio={skipped} inexistentes={missing} -> {summary['snap_dir']}")
    return summary


def cmd_snapshot(args) -> None:
    take_snapshot(args.level)


# --------------------------------------------------------------------------- #
# Comando: track  (bucle de captura ante nuevos avances)
# --------------------------------------------------------------------------- #
def cmd_track(args) -> None:
    print(f"[track] iniciando. intervalo={args.interval}s nivel<= {args.level or 'todos'}")
    print("[track] Ctrl-C para detener.")
    last_version = None
    while True:
        try:
            st = get_status()
            if st["version"] != last_version:
                print(f"[track] NUEVO avance detectado: v{st['version']} "
                      f"({st['iso']}) -- capturando...")
                take_snapshot(args.level)
                last_version = st["version"]
            else:
                print(f"[track] sin cambios (v{st['version']}) {_utc_now()}")
        except Exception as exc:  # noqa: BLE001
            print(f"[track] error (continuo): {exc}")
        time.sleep(args.interval)


# --------------------------------------------------------------------------- #
# Comando: timeseries  (extrae la serie temporal del 'historico' embebido)
# --------------------------------------------------------------------------- #
def cmd_timeseries(args) -> None:
    """
    Extrae la linea temporal de mesas escrutadas por scope. Usa el snapshot
    mas reciente de cada scope (el 'historico' embebido contiene TODOS los
    avances, asi que un solo snapshot reconstruye la serie completa).
    """
    _ensure_dirs()
    if not os.path.isdir(RAW_DIR) or not os.listdir(RAW_DIR):
        print("[timeseries] No hay snapshots. Ejecuta 'snapshot' primero.")
        return
    latest = sorted(os.listdir(RAW_DIR))[-1]
    snap_dir = os.path.join(RAW_DIR, latest)
    out = os.path.join(TS_DIR, "mesas_por_avance.csv")
    n_files, n_rows = 0, 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scope_code", "scope_name", "level", "numact",
                    "mdhm", "mdhm_iso", "mesesc", "mesfalt"])
        scopes = {s["code"]: s for s in load_scopes()}
        for fname in sorted(os.listdir(snap_dir)):
            if not fname.endswith(".json"):
                continue
            code = fname.replace(f"ACT_{ELECTION}_", "").replace(".json", "")
            meta = scopes.get(code, {"name": "", "level": ""})
            d = json.load(open(os.path.join(snap_dir, fname), encoding="utf-8"))
            n_files += 1
            hist = d.get("historico", [])
            # incluir el avance actual ademas del historico
            cur = {"numact": d.get("numact"), "mdhm": d.get("mdhm"),
                   "mesesc": d.get("totales", {}).get("act", {}).get("mesesc"),
                   "mesfalt": ""}
            for h in [cur] + hist:
                w.writerow([code, meta["name"], meta["level"], h.get("numact"),
                            h.get("mdhm"), mdhm_to_iso(h.get("mdhm", "")),
                            h.get("mesesc"), h.get("mesfalt", "")])
                n_rows += 1
    print(f"[timeseries] {n_files} scopes, {n_rows} filas -> "
          f"{os.path.relpath(out, ROOT)} (fuente: avance '{latest}')")


# --------------------------------------------------------------------------- #
# Comando: watch  (vigila el % nacional y reporta lider al cruzar un umbral)
# --------------------------------------------------------------------------- #
def get_national() -> dict:
    """Lee el ACT nacional (scope 00) y devuelve avance, % y candidatos lideres."""
    raw = http_get(f"/json/ACT/{ELECTION}/00.json", bust=str(time.time()))
    d = json.loads(raw)
    tot = d.get("totales", {}).get("act", {})
    try:
        metota = int(tot.get("metota", "0") or 0)
        mesesc = int(tot.get("mesesc", "0") or 0)
        pct = (100.0 * mesesc / metota) if metota else 0.0
    except ValueError:
        mesesc, metota, pct = 0, 0, 0.0
    leaders = []
    for p in d.get("camaras", [{}])[0].get("partotabla", []):
        a = p.get("act", {})
        c = (a.get("cantotabla") or [{}])[0]
        nombre = " ".join(x for x in [c.get("nomcan"), c.get("apecan")] if x)
        try:
            votos = int(a.get("vot", "0") or 0)
        except ValueError:
            votos = 0
        leaders.append({"nombre": nombre, "votos": votos, "pvot": a.get("pvot", "")})
    leaders.sort(key=lambda x: x["votos"], reverse=True)
    return {"numact": d.get("numact"), "mdhm": d.get("mdhm"),
            "iso": mdhm_to_iso(d.get("mdhm", "")), "mesesc": mesesc,
            "metota": metota, "pct": pct, "leaders": leaders}


def _report_leaders(nat: dict) -> None:
    print(f"\n===== REPORTE @ {nat['pct']:.2f}% escrutado "
          f"(avance {nat['numact']}, {nat['iso']}) =====")
    print(f"Mesas informadas: {nat['mesesc']:,} / {nat['metota']:,}")
    top = nat["leaders"][:2]
    for i, l in enumerate(top, 1):
        print(f"  {i}. {l['nombre']:<35} {l['votos']:>10,}  ({l['pvot']})")
    if len(top) >= 2:
        gap = top[0]["votos"] - top[1]["votos"]
        print(f"  Diferencia: {gap:,} votos a favor de {top[0]['nombre']}")
        # Heuristica simple de "quien puede ganar"
        falta = nat["metota"] - nat["mesesc"]
        print(f"  -> LIDERA: {top[0]['nombre']} ({top[0]['pvot']}). "
              f"Faltan {falta:,} mesas por informar.")


def cmd_watch(args) -> None:
    print(f"[watch] vigilando % nacional hasta umbral={args.threshold}% "
          f"(sondeo cada {args.interval}s)")
    while True:
        try:
            nat = get_national()
            print(f"[watch] avance={nat['numact']} {nat['pct']:.2f}% "
                  f"({nat['mesesc']:,}/{nat['metota']:,}) {_utc_now()}")
            if nat["pct"] >= args.threshold and nat["metota"] > 0:
                _report_leaders(nat)
                print(f"\n[watch] UMBRAL {args.threshold}% ALCANZADO. Fin del monitor.")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[watch] error (continuo): {exc}")
        time.sleep(args.interval)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    # Parser padre: --round disponible en todos los subcomandos
    base = argparse.ArgumentParser(add_help=False)
    base.add_argument("--round", type=int, choices=[1, 2], default=2,
                      help="Vuelta: 2=segunda (/v2, activa, default), 1=primera (raiz)")

    p = argparse.ArgumentParser(description="Tracker de boletines Registraduria 2026")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scopes", parents=[base], help="Genera config/scopes.json desde el nomenclator")
    sub.add_parser("status", parents=[base], help="Consulta notification.json (version + mdhm)")

    sp = sub.add_parser("snapshot", parents=[base], help="Captura un snapshot inmutable de todos los scopes")
    sp.add_argument("--level", type=int, default=None,
                    help="Nivel maximo (1=nacional,2=depto,3=municipio)")

    tr = sub.add_parser("track", parents=[base], help="Bucle: captura en cada nuevo avance")
    tr.add_argument("--interval", type=int, default=30, help="Segundos entre sondeos")
    tr.add_argument("--level", type=int, default=None, help="Nivel maximo")

    sub.add_parser("timeseries", parents=[base], help="Exporta CSV de mesas escrutadas por avance")

    wt = sub.add_parser("watch", parents=[base],
                        help="Vigila el % nacional y reporta lider al cruzar un umbral")
    wt.add_argument("--threshold", type=float, default=90.0, help="Umbral %% de mesas informadas")
    wt.add_argument("--interval", type=int, default=60, help="Segundos entre sondeos")

    args = p.parse_args()
    set_round(getattr(args, "round", 2))
    dispatch = {
        "scopes": lambda a: build_scopes(),
        "status": cmd_status,
        "snapshot": cmd_snapshot,
        "track": cmd_track,
        "timeseries": cmd_timeseries,
        "watch": cmd_watch,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
