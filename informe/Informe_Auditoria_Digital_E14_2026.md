# Informe de Auditoría Digital Ciudadana
## Elecciones Presidenciales 2026 — Segunda Vuelta
### Verificación independiente de resultados y formularios E-14

**Fecha:** 22 de junio de 2026
**Alcance:** Boletines de resultados preliminares y formularios E-14 (Delegados) publicados por la Registraduría Nacional del Estado Civil.
**Naturaleza:** Auditoría técnica independiente, reproducible y no destructiva, realizada únicamente sobre información pública.

---

## 1. Resumen ejecutivo

Se realizó una verificación digital de extremo a extremo del proceso de divulgación electoral de la segunda vuelta presidencial 2026, cruzando tres fuentes públicas: (a) el portal de resultados preliminares, (b) el portal de consulta de formularios E-14, y (c) los archivos PDF de las actas.

**Conclusión general: no se encontró evidencia de manipulación.** Los resultados, las actas y sus tiempos de publicación son mutuamente consistentes. No obstante, se identificaron **debilidades de transparencia técnica** en la forma en que se publican las actas digitales —principalmente la **ausencia total de metadatos en los PDF**— que conviene corregir para que cualquier ciudadano pueda auditar de forma autónoma y verificable.

| Verificación | Resultado |
| --- | --- |
| Resultado del conteo (100% mesas) | De La Espriella 49,66% vs Cepeda 48,70% (dif. ≈ 250.820 votos) |
| Reconciliación conteo vs E-14 | 0 municipios con "más E-14 que mesas informadas" |
| Validez temporal de actas (120.611) | 99,90% válidas; **0 publicadas antes del cierre de urnas** |
| Integridad (re-hash) | Línea base establecida; sin republicaciones detectadas |

---

## 2. Metodología

1. **Captura de resultados en el tiempo.** Se registró cada boletín/avance del portal de resultados, con marca de tiempo y huella SHA-256, construyendo la línea temporal de mesas informadas por ámbito territorial (país → departamento → municipio).
2. **Inventario de E-14.** Se obtuvo el catálogo completo de actas publicadas (120.611 al cierre de la captura), cada una identificada por su nombre de archivo, que es un **hash SHA-256** del documento fuente.
3. **Archivo con cadena de custodia.** Se descargaron los 120.611 PDF y se calculó un SHA-256 propio de cada archivo, almacenado en un manifiesto append-only.
4. **Verificación temporal.** Para cada acta se obtuvo su hora real de publicación (cabecera HTTP `Last-Modified` del CDN) y se cruzó contra la línea temporal de reporte de resultados de su municipio.
5. **Monitoreo de integridad.** Se estableció una línea base y un proceso de re-hash periódico que detecta republicaciones, altas y bajas de actas entre corridas.

Todo el proceso es **reproducible**: se apoya en scripts deterministas y archivos intermedios verificables.

---

## 3. Hallazgos

### 3.1 Resultados
Con el 100% de mesas informadas (122.020), el resultado fue estable y la diferencia (≈ 250.820 votos) es muy superior a las mesas pendientes en cualquier momento del conteo, por lo que el resultado fue irreversible mucho antes del cierre.

### 3.2 Reconciliación conteo ↔ E-14
La cantidad de E-14 publicados por municipio nunca superó a las mesas informadas en resultados (0 anomalías de ese tipo). La publicación de imágenes E-14 va naturalmente por detrás del conteo preliminar (que se basa en la transmisión de datos), lo cual es esperado.

### 3.3 Validez temporal de las actas
De 120.611 actas verificadas:
- **120.486 (99,90%) válidas:** publicadas después del cierre de urnas y de forma coherente con el conteo de su municipio.
- **125 (0,10%) marcadas:** publicadas hasta 9 minutos antes del primer reporte agregado de su municipio. **Todas con brecha ≤ 9 minutos**, atribuible a la **granularidad de muestreo (~5 min)** de los boletines de resultados frente a la marca exacta del `Last-Modified`. No constituyen anomalía sustantiva.
- **0 actas publicadas antes del cierre de urnas (16:00),** que sería el indicador más fuerte de irregularidad.

### 3.4 Integridad
No se detectaron republicaciones (mismo puesto/mesa con un E-14 distinto) ni bajas durante el período observado. El monitoreo continúa para detectar cambios posteriores.

### 3.5 Hallazgo técnico crítico para la transparencia — Ausencia de metadatos
**Los PDF de los E-14 no contienen ningún metadato.** Son imágenes escaneadas, sin diccionario de información y **sin fecha de creación ni de modificación** (`CreationDate` / `ModDate` ausentes). En consecuencia:
- Al descargar un acta, **el archivo no declara cuándo fue creado, escaneado o publicado.**
- La única forma de conocer su hora de publicación es la cabecera `Last-Modified` del servidor, que **no es visible para el ciudadano** y puede perderse al copiar o redistribuir el archivo.
- Esto **dificulta la auditoría ciudadana autónoma**: quien recibe un PDF no puede, por sí solo, situarlo en el tiempo ni verificar su autenticidad sin volver al portal.

---

## 4. Recomendaciones a la Registraduría Nacional del Estado Civil

Orientadas a que la auditoría digital sea **más transparente, verificable y autónoma** para cualquier ciudadano.

1. **Incluir metadatos en cada PDF de E-14.** Como mínimo `CreationDate` (momento de digitalización/transmisión) y `ModDate`, además de campos como mesa, puesto, zona, municipio y departamento. *Hoy el archivo no dice cuándo fue creado; debería decirlo.*

2. **Sellado de tiempo confiable (TSA).** Aplicar un sello de tiempo criptográfico (RFC 3161) a cada acta al publicarla, de modo que la hora de publicación viaje **dentro** del archivo y sea verificable sin depender del servidor.

3. **Firma digital de las actas.** Firmar criptográficamente cada E-14 (o un manifiesto que las agrupe) con un certificado de la Registraduría, para que cualquiera pueda comprobar autenticidad e integridad de forma offline.

4. **Publicar un manifiesto de integridad abierto.** Un archivo público y firmado que liste, por mesa: identificador, hash del acta, fecha-hora de publicación y número de versión. Esto convierte la verificación en un proceso de un clic.

5. **Exponer la fecha de publicación por mesa en los datos abiertos.** El campo de fecha de publicación existe en el modelo interno pero **no se expone** en los datos estáticos que consume el portal; publicarlo elimina la necesidad de inferir tiempos.

6. **Historial de versiones visible.** Si un E-14 se republica (corrección, re-escaneo), conservar y mostrar públicamente la versión anterior y el motivo. La trazabilidad de cambios es esencial para la confianza.

7. **Acceso abierto para auditores.** Ofrecer un punto de acceso a datos sin barreras anti-automatización (CAPTCHA) para fines de auditoría/datos abiertos, idealmente con documentación. La apertura controlada fortalece, no debilita, la legitimidad.

8. **Consistencia de granularidad temporal.** Publicar la línea temporal de resultados con marcas de tiempo más finas (o exactas) reduce los falsos positivos como las 125 actas marcadas en este informe.

9. **Documentar el esquema de hash.** Aclarar públicamente qué representa el hash que da nombre a cada PDF (qué se hashea exactamente), para que los auditores puedan recomputarlo y verificarlo.

---

## 5. Veredicto final

> **A nivel de datos y tiempos, el proceso de divulgación de la segunda vuelta presidencial 2026 se observa íntegro y consistente.** El resultado es claro e irreversible; las actas E-14 coinciden con lo reportado y ninguna se publicó antes del cierre de urnas. Las 125 actas marcadas corresponden a artefactos de muestreo, no a irregularidades.
>
> **Sin embargo, la transparencia digital es mejorable.** El obstáculo principal es que **las actas se publican como imágenes sin metadatos: el ciudadano que descarga un E-14 no puede saber, a partir del propio archivo, cuándo fue creado o publicado, ni verificar su autenticidad de forma autónoma.** Implementar metadatos, sellado de tiempo y firma digital (recomendaciones 1–4) elevaría sustancialmente la confianza pública sin cambiar el fondo del proceso.
>
> En síntesis: **resultado confiable; mecanismo de publicación perfectible.** La adopción de estándares abiertos de integridad y trazabilidad permitiría que la verificación dejara de depender de auditores técnicos y quedara al alcance de cualquier ciudadano.

---

*Informe elaborado a partir de información pública, con métodos reproducibles. Los artefactos de soporte (manifiestos de hashes, líneas temporales, clasificación de validez y diffs de integridad) están disponibles para su contraste.*
