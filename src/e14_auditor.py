#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e14_auditor.py
==============
Auditoria de los formularios E-14 (Delegados) de la Segunda Vuelta
Presidencial 2026 y su reconciliacion contra las mesas informadas en el
portal de resultados (capturadas por registraduria_tracker.py).

PORTAL E-14: https://e14segundavueltapresidente.registraduria.gov.co
DESCUBRIMIENTO CLAVE (2026-06-21): el portal (Angular + Akamai) NO usa su API
GraphQL (AppSync/Cognito/reCAPTCHA) para los datos; sirve **JSON estaticos**
bajo /assets/temis/divipol_json/ (config divipolSource=true). Por eso NO hace
falta resolver el captcha ni firmar SigV4: todo se baja con headers de navegador.

FUENTES (estaticas, sin captcha):
  - /assets/temis/divipol_json/allTransmissionCodes.json
        -> TODA la metadata de E-14 por mesa. Dos grupos: status11 (publicado)
           y status3. Cada nodo:
             numberStand, expectedName (=<hash>.pdf), idTransmissionCodeStatus,
             idCorporationCode, idStand, standCode, idZoneCode,
             idDepartmentCode, municipalityCode
  - /assets/temis/divipol_json/allMviewGetProgressByMunicipalityAndCorporations.json
        -> por municipio: expected (mesas) y published (E-14 publicados)

EL "HASH DE LA MESA":
  El nombre del PDF de cada E-14 es un SHA-256 de 64 hex (expectedName). Es la
  huella oficial del documento fuente que transmitieron los jurados. NO coincide
  con el SHA-256 del PDF servido (el PDF es un envoltorio determinista distinto).
  Por eso guardamos AMBOS:
    - name_hash  : el hash oficial (nombre del archivo) -> detecta republicaciones
    - pdf_sha256 : nuestro hash del PDF descargado       -> integridad del archivo

URL del PDF (patron confirmado):
  /assets/temis/pdf/{depto}/{muni}/{standCode:3}/{zona}/{numberStand}/{corp}/{expectedName}
  ej: /assets/temis/pdf/60/001/001/01/001/PRE/<hash>.pdf

USO:
  python e14_auditor.py fetch-data      # baja los JSON estaticos del portal E-14
  python e14_auditor.py index           # -> data/e14/mesas_e14.csv (hash por mesa)
  python e14_auditor.py reconcile       # cruza E-14 publicados vs mesas informadas
  python e14_auditor.py pdfs --dept 60 --muni 001   # baja+hashea PDFs de un municipio
  python e14_auditor.py pdfs --dept 60              # todo un departamento
"""

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
BASE = "https://e14segundavueltapresidente.registraduria.gov.co"
DIVIPOL = "/assets/temis/divipol_json"
CORP_ACRONYM = {"001": "PRE"}  # idCorporationCode -> acronimo en la ruta del PDF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E14_DIR = os.path.join(ROOT, "data", "e14")
RAW_DIR = os.path.join(E14_DIR, "raw")          # JSON estaticos crudos
PDF_DIR = os.path.join(E14_DIR, "pdf")          # PDFs descargados (archivo inmutable)
MESAS_CSV = os.path.join(E14_DIR, "mesas_e14.csv")
RECON_CSV = os.path.join(E14_DIR, "reconciliacion.csv")
PDF_MANIFEST = os.path.join(E14_DIR, "pdf_manifest.csv")

# Resultados (del otro tracker) para la reconciliacion
RESULTS_RAW = os.path.join(ROOT, "data", "raw")

# Akamai exige headers completos de navegador o cuelga la conexion.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="126", "Not?A_Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": BASE + "/home",
    "Connection": "keep-alive",
}
MAX_RETRIES = 5
TIMEOUT = 90


# --------------------------------------------------------------------------- #
def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    for d in (E14_DIR, RAW_DIR, PDF_DIR):
        os.makedirs(d, exist_ok=True)


def http_get(path: str, retries: int = MAX_RETRIES) -> bytes:
    """GET con headers de navegador y reintentos (Akamai da 503 transitorios)."""
    url = path if path.startswith("http") else BASE + path
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                raise
            time.sleep(min(2 ** attempt, 10) + 0.3 * attempt)
    raise last  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# fetch-data: baja los JSON estaticos del portal E-14
# --------------------------------------------------------------------------- #
DATASETS = {
    "allTransmissionCodes.json": f"{DIVIPOL}/allTransmissionCodes.json",
    "progressByMunicipality.json": f"{DIVIPOL}/allMviewGetProgressByMunicipalityAndCorporations.json",
    "progressByDepartment.json": f"{DIVIPOL}/allMviewGetProgressByDepartmentAndCorporations.json",
}


def cmd_fetch_data(_args) -> None:
    _ensure_dirs()
    for name, path in DATASETS.items():
        raw = http_get(path)
        out = os.path.join(RAW_DIR, name)
        with open(out, "wb") as fh:
            fh.write(raw)
        print(f"[fetch-data] {name}: {len(raw):,} bytes -> {os.path.relpath(out, ROOT)}")
    print(f"[fetch-data] OK @ {_utc_now()}")


# --------------------------------------------------------------------------- #
# index: parsea allTransmissionCodes.json -> CSV por mesa (con el hash)
# --------------------------------------------------------------------------- #
def _pdf_path_for(node: dict) -> str:
    # Patron confirmado (2026-06-21):
    #   pdf/{depto}/{muni}/{zona:zfill3}/{standCode}/{numberStand}/{corp}/{expectedName}
    corp = CORP_ACRONYM.get(node.get("idCorporationCode", ""), "PRE")
    return (f"/assets/temis/pdf/{node['idDepartmentCode']}/{node['municipalityCode']}/"
            f"{str(node['idZoneCode']).zfill(3)}/{node['standCode']}/"
            f"{node['numberStand']}/{corp}/{node['expectedName']}")


def _load_transmission() -> list:
    f = os.path.join(RAW_DIR, "allTransmissionCodes.json")
    if not os.path.exists(f):
        raise SystemExit("Falta allTransmissionCodes.json. Ejecuta 'fetch-data' primero.")
    d = json.load(open(f, encoding="utf-8"))["data"]
    out = []
    for group in ("status11", "status3"):
        for n in d.get(group, {}).get("nodes", []):
            out.append(n)
    return out


def cmd_index(_args) -> None:
    _ensure_dirs()
    nodes = _load_transmission()
    rows = 0
    with open(MESAS_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["dept", "muni", "zona", "puesto", "mesa", "status",
                    "name_hash", "pdf_path", "scope_resultados"])
        for n in nodes:
            name = n.get("expectedName", "")
            name_hash = name[:-4] if name.endswith(".pdf") else name
            scope = f"{n['idDepartmentCode']}{n['municipalityCode']}"  # = scope municipio del portal de resultados
            w.writerow([n["idDepartmentCode"], n["municipalityCode"], n["idZoneCode"],
                        n["standCode"], n["numberStand"], n["idTransmissionCodeStatus"],
                        name_hash, _pdf_path_for(n), scope])
            rows += 1
    print(f"[index] {rows:,} mesas con E-14 -> {os.path.relpath(MESAS_CSV, ROOT)}")
    pub = sum(1 for n in nodes if n.get("idTransmissionCodeStatus") == 11)
    print(f"[index] publicados (status11): {pub:,} | otros (status3): {rows - pub:,}")


# --------------------------------------------------------------------------- #
# reconcile: E-14 publicados por municipio vs mesas informadas (resultados)
# --------------------------------------------------------------------------- #
def _load_e14_progress_by_muni() -> dict:
    f = os.path.join(RAW_DIR, "progressByMunicipality.json")
    if not os.path.exists(f):
        raise SystemExit("Falta progressByMunicipality.json. Ejecuta 'fetch-data'.")
    d = json.load(open(f, encoding="utf-8"))["data"]
    edges = d["allMviewGetProgressByMunicipalityAndCorporations"]["edges"]
    out = {}
    for e in edges:
        n = e["node"]
        scope = f"{n['idDepartmentCode']}{n['municipalityCode']}"
        out[scope] = {"name": n.get("municipalityName", ""),
                      "expected": int(n.get("expected") or 0),
                      "published": int(n.get("published") or 0)}
    return out


def _load_results_by_muni() -> dict:
    """Lee el snapshot de resultados mas reciente: mesas informadas por municipio."""
    if not os.path.isdir(RESULTS_RAW) or not os.listdir(RESULTS_RAW):
        return {}
    latest = sorted(os.listdir(RESULTS_RAW))[-1]
    snap = os.path.join(RESULTS_RAW, latest)
    out = {"_avance": latest}
    for fname in os.listdir(snap):
        if not fname.endswith(".json"):
            continue
        scope = fname.replace("ACT_PR_", "").replace(".json", "")
        if len(scope) != 5:   # solo municipios (dept2+muni3)
            continue
        try:
            d = json.load(open(os.path.join(snap, fname), encoding="utf-8"))
            tot = d.get("totales", {}).get("act", {})
            out[scope] = {"mesesc": int(tot.get("mesesc") or 0),
                          "metota": int(tot.get("metota") or 0)}
        except (ValueError, KeyError):
            continue
    return out


def cmd_reconcile(_args) -> None:
    _ensure_dirs()
    e14 = _load_e14_progress_by_muni()
    res = _load_results_by_muni()
    avance = res.pop("_avance", "n/a")
    scopes = sorted(set(e14) | set(k for k in res if k != "_avance"))
    rows, flagged = 0, 0
    tot_inform = tot_e14pub = 0
    with open(RECON_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scope", "municipio", "mesas_informadas_resultados", "mesas_total",
                    "e14_esperados", "e14_publicados", "dif_informadas_vs_e14pub", "flag"])
        for s in scopes:
            e = e14.get(s, {})
            r = res.get(s, {})
            inform = r.get("mesesc", 0)
            e14pub = e.get("published", 0)
            diff = inform - e14pub
            # FLAG: mas E-14 publicados que mesas informadas en resultados = anomalia
            flag = ""
            if e14pub > inform and inform >= 0 and r:
                flag = "E14>INFORMADAS"
                flagged += 1
            elif e.get("expected") and r.get("metota") and e["expected"] != r["metota"]:
                flag = "TOTAL_MESAS_DISTINTO"
            w.writerow([s, e.get("name", ""), inform, r.get("metota", ""),
                        e.get("expected", ""), e14pub, diff, flag])
            tot_inform += inform
            tot_e14pub += e14pub
            rows += 1
    print(f"[reconcile] municipios: {rows} | snapshot resultados: {avance}")
    print(f"[reconcile] TOTAL mesas informadas (resultados): {tot_inform:,}")
    print(f"[reconcile] TOTAL E-14 publicados: {tot_e14pub:,}")
    print(f"[reconcile] brecha (informadas - E14pub): {tot_inform - tot_e14pub:,}")
    print(f"[reconcile] municipios con flag E14>INFORMADAS: {flagged}")
    print(f"[reconcile] -> {os.path.relpath(RECON_CSV, ROOT)}")


# --------------------------------------------------------------------------- #
# pdfs: descarga + SHA-256 de los E-14 de un scope (archivo inmutable)
# --------------------------------------------------------------------------- #
def _append_pdf_manifest(rows: list) -> None:
    new = not os.path.exists(PDF_MANIFEST)
    with open(PDF_MANIFEST, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["captured_at_utc", "dept", "muni", "zona", "puesto", "mesa",
                        "name_hash", "pdf_sha256", "bytes", "local_path"])
        w.writerows(rows)


def _download_one(n: dict):
    """Descarga+hashea un E-14. Devuelve (node, fila_manifest|None, estado)."""
    sub = os.path.join(PDF_DIR, n["idDepartmentCode"], n["municipalityCode"])
    os.makedirs(sub, exist_ok=True)
    local = os.path.join(sub, n["expectedName"])
    if os.path.exists(local):
        return (n, None, "skip")
    try:
        raw = http_get(_pdf_path_for(n))
        if raw[:4] != b"%PDF":
            return (n, None, "err")
        with open(local, "wb") as fh:
            fh.write(raw)
        row = [_utc_now(), n["idDepartmentCode"], n["municipalityCode"],
               n["idZoneCode"], n["standCode"], n["numberStand"],
               n["expectedName"][:-4], hashlib.sha256(raw).hexdigest(),
               len(raw), os.path.relpath(local, ROOT).replace("\\", "/")]
        return (n, row, "ok")
    except Exception:  # noqa: BLE001
        return (n, None, "err")


def cmd_pdfs(args) -> None:
    import concurrent.futures as cf
    _ensure_dirs()
    nodes = _load_transmission()
    sel = [n for n in nodes
           if n.get("idTransmissionCodeStatus") == 11
           and (args.dept is None or n["idDepartmentCode"] == args.dept)
           and (args.muni is None or n["municipalityCode"] == args.muni)]
    print(f"[pdfs] objetivo: {len(sel):,} E-14 publicados "
          f"(dept={args.dept or 'todos'} muni={args.muni or 'todos'}) "
          f"workers={args.workers}")
    rows, ok, skip, err = [], 0, 0, 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (n, row, st) in enumerate(ex.map(_download_one, sel), 1):
            if st == "ok":
                ok += 1; rows.append(row)
            elif st == "skip":
                skip += 1
            else:
                err += 1
            if i % 250 == 0:
                print(f"  ... {i}/{len(sel)} (ok={ok} skip={skip} err={err})")
                _append_pdf_manifest(rows); rows = []
    _append_pdf_manifest(rows)
    print(f"[pdfs] OK descargados={ok} sin_cambio={skip} errores={err} "
          f"-> {os.path.relpath(PDF_DIR, ROOT)} ; manifest: {os.path.relpath(PDF_MANIFEST, ROOT)}")


# --------------------------------------------------------------------------- #
# verify-times: cruza la hora de publicacion del E-14 (Last-Modified) con el
# timeline de reporte de resultados del municipio. Validez temporal.
# --------------------------------------------------------------------------- #
import datetime as _dt
COL_TZ = _dt.timezone(_dt.timedelta(hours=-5))
POLLS_CLOSE = _dt.datetime(2026, 6, 21, 16, 0, tzinfo=COL_TZ)   # cierre de urnas 2a vuelta
TIMES_CSV = os.path.join(E14_DIR, "mesa_times.csv")
VALIDEZ_CSV = os.path.join(E14_DIR, "validez_temporal.csv")


def _http_last_modified(path: str) -> str | None:
    url = path if path.startswith("http") else BASE + path
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.headers.get("Last-Modified")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return None
            time.sleep(min(2 ** attempt, 8))
    return None


def _lm_to_col(http_date: str) -> _dt.datetime:
    t = _dt.datetime.strptime(http_date, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=_dt.timezone.utc)
    return t.astimezone(COL_TZ)


def _mdhm_to_col(mdhm: str) -> _dt.datetime | None:
    if not mdhm or len(mdhm) != 8 or not mdhm.isdigit():
        return None
    return _dt.datetime(2026, int(mdhm[0:2]), int(mdhm[2:4]),
                        int(mdhm[4:6]), int(mdhm[6:8]), tzinfo=COL_TZ)


def _results_timeline_by_muni() -> dict:
    """Por municipio (scope 5 dig): primera hora con mesas>0 y ultima reportada."""
    if not os.path.isdir(RESULTS_RAW) or not os.listdir(RESULTS_RAW):
        return {}
    latest = sorted(os.listdir(RESULTS_RAW))[-1]
    snap = os.path.join(RESULTS_RAW, latest)
    out = {}
    for fname in os.listdir(snap):
        if not fname.endswith(".json"):
            continue
        scope = fname.replace("ACT_PR_", "").replace(".json", "")
        if len(scope) != 5:
            continue
        try:
            d = json.load(open(os.path.join(snap, fname), encoding="utf-8"))
        except (ValueError, OSError):
            continue
        hist = d.get("historico", []) + [{"mdhm": d.get("mdhm"),
                "mesesc": d.get("totales", {}).get("act", {}).get("mesesc", "0")}]
        firsts = [_mdhm_to_col(h.get("mdhm", "")) for h in hist if int(h.get("mesesc") or 0) > 0]
        firsts = [t for t in firsts if t]
        out[scope] = {"first": min(firsts) if firsts else None,
                      "last": _mdhm_to_col(d.get("mdhm", ""))}
    return out


def _classify(pub: _dt.datetime, tl: dict) -> tuple:
    if pub < POLLS_CLOSE:
        return "INVALIDO_ANTES_CIERRE", ""
    first = (tl or {}).get("first")
    if first and pub < first:
        gap = (first - pub).total_seconds() / 60
        return "FLAG_ANTES_REPORTE_MUNI", f"{gap:.0f}min antes del 1er reporte"
    return "VALIDO", ""


def cmd_verify_times(args) -> None:
    import concurrent.futures as cf
    _ensure_dirs()
    nodes = [n for n in _load_transmission()
             if n.get("idTransmissionCodeStatus") == 11
             and (args.dept is None or n["idDepartmentCode"] == args.dept)
             and (args.muni is None or n["municipalityCode"] == args.muni)]
    # cache incremental de Last-Modified ya consultados
    cache = {}
    if os.path.exists(TIMES_CSV):
        for row in csv.DictReader(open(TIMES_CSV, encoding="utf-8")):
            cache[row["name_hash"]] = row["pub_col"]
    pend = [n for n in nodes if n["expectedName"][:-4] not in cache]
    print(f"[verify-times] {len(nodes):,} E-14 (dept={args.dept or 'todos'} "
          f"muni={args.muni or 'todos'}) | en cache: {len(nodes)-len(pend):,} | "
          f"a consultar: {len(pend):,} | workers={args.workers}")

    def head(n):
        lm = _http_last_modified(_pdf_path_for(n))
        return (n, lm)

    new = not os.path.exists(TIMES_CSV)
    fh = open(TIMES_CSV, "a", newline="", encoding="utf-8")
    w = csv.writer(fh)
    if new:
        w.writerow(["dept", "muni", "zona", "puesto", "mesa", "name_hash", "pub_col"])
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for n, lm in ex.map(head, pend):
            pub = _lm_to_col(lm).isoformat() if lm else ""
            cache[n["expectedName"][:-4]] = pub
            w.writerow([n["idDepartmentCode"], n["municipalityCode"], n["idZoneCode"],
                        n["standCode"], n["numberStand"], n["expectedName"][:-4], pub])
            done += 1
            if done % 500 == 0:
                print(f"  ... {done}/{len(pend)}"); fh.flush()
    fh.close()

    # clasificar validez temporal
    timelines = _results_timeline_by_muni()
    counts = {"VALIDO": 0, "FLAG_ANTES_REPORTE_MUNI": 0, "INVALIDO_ANTES_CIERRE": 0, "SIN_FECHA": 0}
    with open(VALIDEZ_CSV, "w", newline="", encoding="utf-8") as out:
        cw = csv.writer(out)
        cw.writerow(["dept", "muni", "zona", "puesto", "mesa", "name_hash",
                     "pub_col", "muni_primer_reporte", "validez", "nota"])
        for n in nodes:
            nh = n["expectedName"][:-4]
            pub_s = cache.get(nh, "")
            scope = f"{n['idDepartmentCode']}{n['municipalityCode']}"
            tl = timelines.get(scope, {})
            first = tl.get("first")
            if not pub_s:
                status, nota = "SIN_FECHA", ""
            else:
                status, nota = _classify(_dt.datetime.fromisoformat(pub_s), tl)
            counts[status] = counts.get(status, 0) + 1
            cw.writerow([n["idDepartmentCode"], n["municipalityCode"], n["idZoneCode"],
                         n["standCode"], n["numberStand"], nh, pub_s,
                         first.isoformat() if first else "", status, nota])
    print(f"[verify-times] clasificacion: {counts}")
    print(f"[verify-times] -> {os.path.relpath(VALIDEZ_CSV, ROOT)}")


# --------------------------------------------------------------------------- #
# integrity: monitor de integridad por re-hash. Detecta republicaciones,
# altas, bajas y cambios de estado de los E-14 entre corridas periodicas.
# --------------------------------------------------------------------------- #
INTEG_DIR = os.path.join(E14_DIR, "integrity")


def _mesa_key(n: dict) -> str:
    # identidad fisica estable de la mesa (puesto global + numero de mesa)
    return f"{n['idStand']}-{n['numberStand']}"


def _build_state() -> dict:
    """Estado actual {clave_mesa: {hash,status,loc}} desde allTransmissionCodes.json."""
    d = json.load(open(os.path.join(RAW_DIR, "allTransmissionCodes.json"),
                       encoding="utf-8"))["data"]
    state = {}
    for group in ("status11", "status3"):
        for n in d.get(group, {}).get("nodes", []):
            state[_mesa_key(n)] = {
                "hash": n["expectedName"][:-4],
                "status": n["idTransmissionCodeStatus"],
                "loc": f"{n['idDepartmentCode']}/{n['municipalityCode']}/"
                       f"{n['idZoneCode']}/{n['standCode']}/{n['numberStand']}",
            }
    return state


def _latest_state_file() -> str | None:
    if not os.path.isdir(INTEG_DIR):
        return None
    snaps = sorted(f for f in os.listdir(INTEG_DIR) if f.startswith("state_"))
    return os.path.join(INTEG_DIR, snaps[-1]) if snaps else None


def cmd_integrity(args) -> None:
    os.makedirs(INTEG_DIR, exist_ok=True)
    # 1) refrescar datos del portal
    raw = http_get(DATASETS["allTransmissionCodes.json"])
    with open(os.path.join(RAW_DIR, "allTransmissionCodes.json"), "wb") as fh:
        fh.write(raw)
    current = _build_state()
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state_path = os.path.join(INTEG_DIR, f"state_{ts}.json")
    json.dump(current, open(state_path, "w", encoding="utf-8"))

    prior_path = None if args.baseline else _latest_state_file_excluding(state_path)
    if args.baseline or not prior_path:
        print(f"[integrity] LINEA BASE guardada: {len(current):,} E-14 "
              f"-> {os.path.relpath(state_path, ROOT)}")
        return

    prior = json.load(open(prior_path, encoding="utf-8"))
    new = [k for k in current if k not in prior]
    removed = [k for k in prior if k not in current]                  # BAJA: critico
    changed = [k for k in current if k in prior and current[k]["hash"] != prior[k]["hash"]]  # REPUBLICACION: critico
    status_chg = [k for k in current if k in prior
                  and current[k]["hash"] == prior[k]["hash"]
                  and current[k]["status"] != prior[k]["status"]]

    diff_path = os.path.join(INTEG_DIR, f"diff_{ts}.csv")
    with open(diff_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tipo", "mesa_key", "loc", "hash_antes", "hash_ahora",
                    "status_antes", "status_ahora"])
        for k in changed:
            w.writerow(["REPUBLICACION", k, current[k]["loc"], prior[k]["hash"],
                        current[k]["hash"], prior[k]["status"], current[k]["status"]])
        for k in removed:
            w.writerow(["BAJA", k, prior[k]["loc"], prior[k]["hash"], "",
                        prior[k]["status"], ""])
        for k in new:
            w.writerow(["ALTA", k, current[k]["loc"], "", current[k]["hash"],
                        "", current[k]["status"]])
        for k in status_chg:
            w.writerow(["CAMBIO_ESTADO", k, current[k]["loc"], prior[k]["hash"],
                        current[k]["hash"], prior[k]["status"], current[k]["status"]])
    base = os.path.basename(prior_path)
    print(f"[integrity] comparado contra {base}")
    print(f"  ALTA (nuevas):            {len(new):,}")
    print(f"  REPUBLICACION (hash != ): {len(changed):,}   <-- AUDITAR")
    print(f"  BAJA (desaparecidas):     {len(removed):,}   <-- AUDITAR")
    print(f"  CAMBIO_ESTADO:            {len(status_chg):,}")
    print(f"  sin cambios:              {len(current)-len(new)-len(changed)-len(status_chg):,}")
    print(f"[integrity] diff -> {os.path.relpath(diff_path, ROOT)}")


def _latest_state_file_excluding(exclude: str) -> str | None:
    if not os.path.isdir(INTEG_DIR):
        return None
    snaps = sorted(f for f in os.listdir(INTEG_DIR)
                   if f.startswith("state_") and os.path.join(INTEG_DIR, f) != exclude)
    return os.path.join(INTEG_DIR, snaps[-1]) if snaps else None


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description="Auditor E-14 Segunda Vuelta 2026")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch-data", help="Baja los JSON estaticos del portal E-14")
    sub.add_parser("index", help="Genera CSV de hash por mesa")
    sub.add_parser("reconcile", help="Cruza E-14 publicados vs mesas informadas")
    pf = sub.add_parser("pdfs", help="Descarga+hashea los PDF de E-14 de un scope")
    pf.add_argument("--dept", default=None, help="idDepartmentCode (ej 60)")
    pf.add_argument("--muni", default=None, help="municipalityCode (ej 001)")
    pf.add_argument("--workers", type=int, default=5, help="Descargas concurrentes (default 5)")
    vt = sub.add_parser("verify-times",
                        help="Cruza hora de publicacion del E-14 (Last-Modified) vs reporte de resultados")
    vt.add_argument("--dept", default=None, help="idDepartmentCode (ej 60)")
    vt.add_argument("--muni", default=None, help="municipalityCode (ej 001)")
    vt.add_argument("--workers", type=int, default=8, help="HEAD concurrentes (default 8)")
    ig = sub.add_parser("integrity",
                        help="Monitor de integridad: detecta republicaciones/altas/bajas entre corridas")
    ig.add_argument("--baseline", action="store_true", help="Guardar linea base (primera vez)")
    args = p.parse_args()
    {"fetch-data": cmd_fetch_data, "index": cmd_index,
     "reconcile": cmd_reconcile, "pdfs": cmd_pdfs,
     "verify-times": cmd_verify_times, "integrity": cmd_integrity}[args.cmd](args)


if __name__ == "__main__":
    main()
