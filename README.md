# 🗳️ Verificador Electoral — Registraduría (Colombia)

Herramientas **abiertas, reproducibles y deterministas** para auditar de forma
independiente la divulgación de resultados y los formularios **E-14** de las
elecciones colombianas. Construido durante las **Presidenciales 2026 — Segunda
Vuelta**, pensado para reutilizarse en futuras elecciones.

> **Qué hace:** captura los boletines de resultados con marca de tiempo y hash,
> archiva las actas E-14 con su huella SHA-256, **reconcilia** el conteo contra las
> actas publicadas, **verifica la coherencia temporal** (que ninguna acta se publique
> antes del cierre de urnas) y **monitorea la integridad** (detecta republicaciones).

---

## ✨ Características

- **Sin dependencias pesadas:** el núcleo usa solo la librería estándar de Python.
- **Cadena de custodia:** todo snapshot queda con SHA-256 + timestamp en manifiestos
  append-only.
- **Reproducible:** cualquiera puede re-ejecutar y obtener los mismos artefactos.
- **No invasivo:** solo lee información pública; no descarga nada que requiera
  saltar CAPTCHAs ni autenticación.
- **Informe automático** en PDF con recomendaciones y veredicto.

## 📁 Estructura

```
verificador-electoral-co/
├── README.md
├── requirements.txt
├── LICENSE
├── src/
│   ├── registraduria_tracker.py   # Captura de resultados en el tiempo
│   ├── e14_auditor.py             # Inventario, reconciliación, validez temporal, integridad
│   ├── generar_informe_pdf.py     # Informe PDF
│   └── run_integrity.bat          # Runner para el monitoreo periódico (Windows)
├── docs/
│   ├── fuentes-de-datos.md        # Endpoints/formatos descubiertos (clave para reusar)
│   └── metodologia.md             # Las 5 capas de verificación
├── informe/
│   ├── Informe_Auditoria_Digital_E14_2026.md
│   └── Informe_Auditoria_Digital_E14_2026.pdf
└── data/                          # Generada al ejecutar (NO se versiona; ver .gitignore)
```

## 🚀 Uso rápido

```bash
# (opcional) entorno e instalación
pip install -r requirements.txt   # solo necesario para el informe PDF

cd src

# --- 1) Resultados (durante el conteo en vivo) ---
python registraduria_tracker.py status                 # último boletín publicado
python registraduria_tracker.py track --interval 30    # captura cada nuevo boletín
python registraduria_tracker.py timeseries             # línea temporal mesas/hora

# --- 2) E-14: inventario y archivo ---
python e14_auditor.py fetch-data        # baja los JSON del portal de E-14
python e14_auditor.py index             # -> mesas_e14.csv (hash por mesa)
python e14_auditor.py pdfs --dept 05    # baja+hashea PDFs (por depto/municipio)

# --- 3) Reconciliación conteo vs E-14 ---
python e14_auditor.py reconcile         # -> reconciliacion.csv

# --- 4) Validez temporal de las actas ---
python e14_auditor.py verify-times      # -> validez_temporal.csv, actas_marcadas.csv

# --- 5) Integridad (re-hash) ---
python e14_auditor.py integrity --baseline   # primera vez
python e14_auditor.py integrity              # corridas posteriores -> diff_*.csv

# --- Informe PDF ---
python generar_informe_pdf.py
```

## ⏱️ Monitoreo periódico de integridad

El registro automático no se incluye por seguridad; actívalo tú una vez:

```cmd
:: Windows (Programador de tareas) — corre el chequeo cada día a las 09:00
schtasks /Create /TN "E14_Integridad_Diaria" /TR "%CD%\src\run_integrity.bat" /SC DAILY /ST 09:00 /F
```

## 🔁 Adaptar a una nueva elección

Los dominios cambian en cada elección. Antes de usar:

1. Abre el sitio de resultados y el de E-14 e **inspecciona el bundle JS** del SPA.
2. Busca `VITE_SERVER_URL`, `graphqlUrl`, o rutas `/json/...` y `/assets/.../divipol_json/...`.
3. Actualiza las constantes al inicio de los scripts:
   - `registraduria_tracker.py`: `BASE_HOST`, `ROUND_PREFIX`, `ELECTION`.
   - `e14_auditor.py`: `BASE`, `DIVIPOL`, `CORP_ACRONYM`, `POLLS_CLOSE`.

Detalles completos en [`docs/fuentes-de-datos.md`](docs/fuentes-de-datos.md).

## 📊 Resultados de la auditoría 2026 (2ª vuelta)

- **120.611 actas E-14** verificadas.
- **99,90%** temporalmente válidas; **0** publicadas antes del cierre de urnas.
- **0** municipios con "más E-14 que mesas informadas".
- **Veredicto:** resultado confiable e íntegro; el mecanismo de publicación es
  perfectible (las actas se publican como **imágenes sin metadatos ni firma**).

Informe completo y recomendaciones a la Registraduría en
[`informe/`](informe/Informe_Auditoria_Digital_E14_2026.pdf).

## ⚖️ Aviso

Proyecto **ciudadano e independiente**, sin afiliación con la Registraduría Nacional
del Estado Civil. Usa exclusivamente datos públicos y métodos no destructivos. El
objetivo es la **transparencia y la verificabilidad**, no la sustitución de los
mecanismos oficiales de escrutinio.

## 📄 Licencia

MIT — ver [`LICENSE`](LICENSE). Úsalo, mejóralo y compártelo libremente.
