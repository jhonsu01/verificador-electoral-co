# Fuentes de datos (cómo publican los datos la Registraduría)

> Documenta los endpoints y formatos descubiertos para las Elecciones Presidenciales
> 2026 — Segunda Vuelta. **Para futuras elecciones los dominios cambian**; actualiza
> las constantes al inicio de cada script (`BASE_HOST`/`BASE`/`ROUND_PREFIX`).

---

## 1. Portal de Resultados (conteo preliminar)

- **Sitio:** `https://resultados.registraduria.gov.co` (SPA Vite sobre S3 + CloudFront).
- **2ª vuelta** vive bajo el prefijo **`/v2`** (el frontend usa `VITE_SERVER_URL="/v2"`).
  La raíz `/` es 1ª vuelta y queda congelada.
- **Datos = JSON estático** (no API dinámica):

| Endpoint | Contenido |
| --- | --- |
| `/v2/json/notification.json` | Versión + `mdhm` del último boletín (sondeo barato, ~71 bytes) |
| `/v2/json/nomenclator.json` | Árbol territorial (país, 34 deptos, 1.189 municipios) |
| `/v2/json/ACT/PR/{scope}.json` | Resultados + `historico` (serie temporal de avances) por ámbito |
| `/v2/json/web/config.json` | Estado del portal (isOpen, fase, etc.) |

- **`scope` (DIVIPOL):** `00` = nacional, `01` = departamento, `01001` = municipio
  (depto 2 díg + municipio 3 díg). Máxima granularidad: **municipio**.
- **Campos útiles de `ACT`:** `numact` (nº boletín), `mdhm` (timestamp `MMDDHHmm`,
  hora Colombia UTC-5), `totales.act.{metota,mesesc,meserr}` (mesas totales /
  escrutadas / con error), y `historico[]` (todos los avances pasados).
- **Anti-bot:** requiere `User-Agent` de navegador; CloudFront limita el ratio
  (usar backoff y ≤ 6 hilos).

## 2. Portal de E-14 (actas digitalizadas)

- **Sitio:** `https://e14segundavueltapresidente.registraduria.gov.co` (Angular sobre Akamai).
- **Clave:** el portal **NO usa su API GraphQL** (AppSync/Cognito/reCAPTCHA) para los
  datos. Usa **JSON estáticos** (`divipolSource=true`). Por eso **no hay que resolver
  el CAPTCHA**: todo se baja con cabeceras completas de navegador (Akamai cuelga sin ellas).

| Endpoint | Contenido |
| --- | --- |
| `/assets/temis/divipol_json/allTransmissionCodes.json` | Catálogo de E-14 por mesa (grupos `status11`=publicado, `status3`) |
| `/assets/temis/divipol_json/allMviewGetProgressByMunicipalityAndCorporations.json` | Por municipio: `expected` (mesas) vs `published` (E-14) |
| `/assets/temis/divipol_json/departmentsTree.json` | Árbol geográfico hasta puesto |

- **Nodo de `allTransmissionCodes`:** `numberStand` (mesa), `expectedName`
  (=`<hash>.pdf`), `idTransmissionCodeStatus`, `standCode` (puesto), `idZoneCode`
  (zona), `idDepartmentCode`, `municipalityCode`, `idStand`.
- **El nombre del PDF es un SHA-256** (64 hex) del documento fuente = la "huella" de
  cada acta (sirve para detectar republicaciones).

### URL del PDF de cada E-14 (patrón confirmado)
```
/assets/temis/pdf/{depto}/{muni}/{zona:zfill3}/{standCode}/{numberStand}/{corp}/{expectedName}
```
- `corp`: `idCorporationCode "001"` → `"PRE"`.
- **OJO:** el 3er segmento es la **ZONA** (no el puesto). Confundirlos solo falla
  cuando zona ≠ puesto.
- Ej: `/assets/temis/pdf/60/001/002/01/013/PRE/<hash>.pdf`

### La hora de publicación de cada acta
- **Los PDF NO traen metadatos** (imagen escaneada; sin `CreationDate`/`ModDate`).
- La hora real de publicación se obtiene de la cabecera HTTP **`Last-Modified`**
  (UTC → Colombia UTC-5), vía una petición `HEAD`.
- El SHA-256 del PDF servido **no** coincide con el nombre-hash (el nombre hashea el
  documento fuente, no el PDF de entrega). Por eso se guardan ambos.

## 3. Notas de reproducibilidad

- Todo es **información pública** y los métodos son deterministas y reproducibles.
- Para una nueva elección: identificar los nuevos dominios (inspeccionar el bundle JS
  del SPA en busca de `VITE_SERVER_URL` / `graphqlUrl` / rutas `/json/` o
  `/assets/.../divipol_json/`) y actualizar las constantes de los scripts.
