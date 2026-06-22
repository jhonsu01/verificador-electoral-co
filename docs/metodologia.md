# Metodología de verificación

Auditoría digital **independiente, reproducible y no destructiva**, sobre información
pública. Cinco capas, cada una con su comando.

## 1. Captura de resultados en el tiempo
`registraduria_tracker.py` sondea `notification.json` y, en cada nuevo boletín,
guarda un snapshot inmutable de todos los ámbitos (nacional → departamento →
municipio) con **SHA-256 + timestamp**. Reconstruye la línea temporal de mesas
informadas. Salida: `data/raw/avance_NNNN/`, `data/manifest.csv`.

## 2. Inventario y archivo de E-14
`e14_auditor.py fetch-data` + `index` descargan el catálogo completo de actas y lo
vuelcan a `mesas_e14.csv` (una fila por mesa con su **hash oficial**, estado y la
ruta del PDF). `pdfs` descarga los PDF y calcula un **SHA-256 propio** de cada uno
(cadena de custodia en `pdf_manifest.csv`).

## 3. Reconciliación conteo ↔ E-14
`e14_auditor.py reconcile` cruza, por municipio, **mesas informadas** (resultados)
contra **E-14 publicados**. Bandera roja: más E-14 que mesas informadas. Salida:
`reconciliacion.csv`.

## 4. Verificación temporal (validez)
`e14_auditor.py verify-times` obtiene la hora de publicación de cada acta
(`Last-Modified`) y la cruza con la línea temporal de su municipio.

| Clasificación | Significado |
| --- | --- |
| `VALIDO` | Publicada tras el cierre de urnas y coherente con el conteo |
| `FLAG_ANTES_REPORTE_MUNI` | Apareció antes del 1er reporte agregado del municipio (revisar; suele ser artefacto de muestreo) |
| `INVALIDO_ANTES_CIERRE` | Publicada antes del cierre de urnas → imposible (señal fuerte de irregularidad) |

Salidas: `mesa_times.csv` (caché de horas), `validez_temporal.csv`, `actas_marcadas.csv`.

## 5. Integridad por re-hash periódico
`e14_auditor.py integrity --baseline` fija una línea base; corridas posteriores
(`integrity`) detectan **republicaciones** (mismo puesto/mesa con hash distinto),
**altas**, **bajas** y **cambios de estado**. Salidas en `data/e14/integrity/`
(`state_*.json`, `diff_*.csv`). Automatizable con `run_integrity.bat` + el
Programador de tareas de Windows (ver README).

## Limitaciones conocidas
- La granularidad máxima del portal de resultados es **municipio**; no hay timeline
  por mesa individual, por lo que la validez temporal se evalúa contra la ventana de
  reporte del municipio (de ahí los falsos positivos de pocos minutos).
- Los PDF carecen de metadatos: la hora depende del `Last-Modified` del servidor.
- Esta auditoría verifica **consistencia de datos y tiempos**, no el conteo de votos
  manuscritos (eso requeriría OCR de las actas — capa futura).
