#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera el Informe de Auditoria Digital E-14 2026 en PDF (reportlab)."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "informe", "Informe_Auditoria_Digital_E14_2026.pdf")

AZUL = colors.HexColor("#003057")      # azul institucional
AZUL2 = colors.HexColor("#1a4d7a")
GRIS = colors.HexColor("#5b5b5b")
AMBAR = colors.HexColor("#FFC53D")
VERDE = colors.HexColor("#1b7a3d")
ROJO = colors.HexColor("#b00020")

ss = getSampleStyleSheet()
def st(name, **kw):
    base = kw.pop("parent", ss["Normal"])
    return ParagraphStyle(name, parent=base, **kw)

H_TITLE = st("t", fontName="Helvetica-Bold", fontSize=20, textColor=AZUL, leading=24, spaceAfter=4)
H_SUB = st("s", fontName="Helvetica", fontSize=12, textColor=AZUL2, leading=16, spaceAfter=2)
H_SUB2 = st("s2", fontName="Helvetica-Oblique", fontSize=10.5, textColor=GRIS, leading=14)
H1 = st("h1", fontName="Helvetica-Bold", fontSize=13.5, textColor=AZUL, spaceBefore=14, spaceAfter=6, leading=16)
H2 = st("h2", fontName="Helvetica-Bold", fontSize=11, textColor=AZUL2, spaceBefore=8, spaceAfter=3, leading=14)
BODY = st("b", fontName="Helvetica", fontSize=10, leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6)
BUL = st("bul", parent=BODY, leftIndent=14, bulletIndent=2, spaceAfter=3)
SMALL = st("sm", fontName="Helvetica-Oblique", fontSize=8.5, textColor=GRIS, leading=11)
META = st("meta", fontName="Helvetica", fontSize=9.5, textColor=GRIS, leading=13)
CELL = st("cell", fontName="Helvetica", fontSize=9, leading=12)
CELLB = st("cellb", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.white)
VERD = st("verd", fontName="Helvetica", fontSize=10.5, leading=15.5, alignment=TA_JUSTIFY, textColor=colors.HexColor("#15324a"))


def P(t, s=BODY): return Paragraph(t, s)
def rule(c=AZUL, w=1.2): return HRFlowable(width="100%", thickness=w, color=c, spaceBefore=4, spaceAfter=8)


def info_table(rows, header):
    data = [[Paragraph(header[0], CELLB), Paragraph(header[1], CELLB)]]
    for a, b in rows:
        data.append([Paragraph(a, CELL), Paragraph(b, CELL)])
    t = Table(data, colWidths=[8.4 * cm, 7.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5d3e0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def verdict_box(parts):
    inner = [Paragraph(x, VERD) for x in parts]
    t = Table([[inner]], colWidths=[16 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eaf3ea")),
        ("BOX", (0, 0), (-1, -1), 1.2, VERDE),
        ("LINEBEFORE", (0, 0), (0, -1), 4, VERDE),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRIS)
    canvas.drawString(2 * cm, 1.1 * cm, "Auditoria Digital Ciudadana — Elecciones Presidenciales 2026 (2a vuelta)")
    canvas.drawRightString(19 * cm, 1.1 * cm, f"Pag. {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#c5d3e0"))
    canvas.line(2 * cm, 1.4 * cm, 19 * cm, 1.4 * cm)
    canvas.restoreState()


def build():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = SimpleDocTemplate(OUT, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            title="Informe de Auditoria Digital E-14 2026")
    s = []
    # --- Encabezado ---
    s += [P("Informe de Auditoría Digital Ciudadana", H_TITLE),
          P("Elecciones Presidenciales 2026 — Segunda Vuelta", H_SUB),
          P("Verificación independiente de resultados y formularios E-14", H_SUB2),
          Spacer(1, 6), rule()]
    s += [info_table([
        ("Fecha", "22 de junio de 2026"),
        ("Emisor", "Auditoría ciudadana independiente"),
        ("Alcance", "Boletines de resultados y formularios E-14 (Delegados)"),
        ("Naturaleza", "Técnica, reproducible, no destructiva, sobre información pública"),
    ], ("Campo", "Detalle")), Spacer(1, 10)]

    # 1. Resumen
    s += [P("1. Resumen ejecutivo", H1)]
    s += [P("Se realizó una verificación digital de extremo a extremo de la divulgación electoral de la segunda vuelta presidencial 2026, cruzando tres fuentes públicas: el portal de resultados preliminares, el portal de consulta de formularios E-14 y los archivos PDF de las actas.", BODY)]
    s += [P("<b>Conclusión general: no se encontró evidencia de manipulación.</b> Los resultados, las actas y sus tiempos de publicación son mutuamente consistentes. No obstante, se identificaron <b>debilidades de transparencia técnica</b> en la publicación de las actas digitales —principalmente la <b>ausencia total de metadatos en los PDF</b>— que conviene corregir para habilitar la auditoría ciudadana autónoma.", BODY)]
    s += [info_table([
        ("Resultado del conteo (100% mesas)", "De La Espriella 49,66% vs Cepeda 48,70% (dif. ≈ 250.820 votos)"),
        ("Reconciliación conteo vs E-14", "0 municipios con “más E-14 que mesas informadas”"),
        ("Validez temporal (120.611 actas)", "99,90% válidas; <b>0 publicadas antes del cierre</b>"),
        ("Integridad (re-hash)", "Línea base establecida; sin republicaciones detectadas"),
    ], ("Verificación", "Resultado")), Spacer(1, 4)]

    # 2. Metodologia
    s += [P("2. Metodología", H1)]
    for t in [
        "<b>Captura de resultados en el tiempo:</b> cada boletín del portal de resultados con marca de tiempo y huella SHA-256, reconstruyendo la línea temporal de mesas informadas (país → departamento → municipio).",
        "<b>Inventario de E-14:</b> catálogo completo de actas publicadas (120.611 al cierre de la captura); cada nombre de archivo es un hash SHA-256 del documento fuente.",
        "<b>Archivo con cadena de custodia:</b> descarga de los 120.611 PDF y cálculo de un SHA-256 propio por archivo en un manifiesto append-only.",
        "<b>Verificación temporal:</b> hora real de publicación de cada acta (cabecera HTTP <i>Last-Modified</i>) cruzada contra la línea temporal de su municipio.",
        "<b>Monitoreo de integridad:</b> línea base y re-hash periódico que detecta republicaciones, altas y bajas de actas.",
    ]:
        s += [Paragraph("•&nbsp;&nbsp;" + t, BUL)]
    s += [Spacer(1, 2)]

    # 3. Hallazgos
    s += [P("3. Hallazgos", H1)]
    s += [P("3.1 Resultados", H2),
          P("Con el 100% de mesas informadas (122.020), el resultado fue estable; la diferencia (≈ 250.820 votos) superó ampliamente las mesas pendientes en cualquier momento, por lo que fue irreversible mucho antes del cierre del conteo.", BODY)]
    s += [P("3.2 Reconciliación conteo ↔ E-14", H2),
          P("La cantidad de E-14 publicados por municipio nunca superó a las mesas informadas (0 anomalías). La publicación de imágenes E-14 va por detrás del conteo preliminar —que se basa en la transmisión de datos—, lo cual es esperado.", BODY)]
    s += [P("3.3 Validez temporal de las actas", H2)]
    for t in [
        "<b>120.486 (99,90%) válidas:</b> publicadas tras el cierre y coherentes con el conteo de su municipio.",
        "<b>125 (0,10%) marcadas:</b> publicadas hasta 9 minutos antes del primer reporte agregado de su municipio. Todas con brecha ≤ 9 min, atribuible a la granularidad de muestreo (~5 min) de los boletines frente a la marca exacta del <i>Last-Modified</i>. No son anomalía sustantiva.",
        "<b>0 actas publicadas antes del cierre de urnas (16:00):</b> el indicador más fuerte de irregularidad está en cero.",
    ]:
        s += [Paragraph("•&nbsp;&nbsp;" + t, BUL)]
    s += [P("3.4 Integridad", H2),
          P("No se detectaron republicaciones (mismo puesto/mesa con un E-14 distinto) ni bajas en el período observado. El monitoreo continúa para detectar cambios posteriores.", BODY)]

    s += [KeepTogether([
        P("3.5 Hallazgo técnico crítico — Ausencia de metadatos", H2),
        Paragraph("<b>Los PDF de los E-14 no contienen ningún metadato.</b> Son imágenes escaneadas, sin diccionario de información y <b>sin fecha de creación ni de modificación</b> (CreationDate / ModDate ausentes). En consecuencia:", BODY),
        Paragraph("•&nbsp;&nbsp;Al descargar un acta, <b>el archivo no declara cuándo fue creado, escaneado o publicado.</b>", BUL),
        Paragraph("•&nbsp;&nbsp;La única forma de conocer su hora de publicación es la cabecera <i>Last-Modified</i> del servidor, que <b>no es visible para el ciudadano</b> y se pierde al copiar o redistribuir el archivo.", BUL),
        Paragraph("•&nbsp;&nbsp;Esto <b>dificulta la auditoría ciudadana autónoma:</b> quien recibe un PDF no puede situarlo en el tiempo ni verificar su autenticidad sin volver al portal.", BUL),
    ])]

    # 4. Recomendaciones
    s += [P("4. Recomendaciones a la Registraduría Nacional del Estado Civil", H1)]
    recs = [
        ("Incluir metadatos en cada PDF.", "Como mínimo CreationDate (digitalización/transmisión) y ModDate, más mesa, puesto, zona, municipio y departamento. <i>Hoy el archivo no dice cuándo fue creado; debería decirlo.</i>"),
        ("Sellado de tiempo confiable (TSA).", "Sello criptográfico (RFC 3161) por acta, de modo que la hora viaje dentro del archivo y sea verificable sin depender del servidor."),
        ("Firma digital de las actas.", "Firmar cada E-14 (o un manifiesto que las agrupe) con certificado de la Registraduría, para comprobar autenticidad e integridad de forma offline."),
        ("Manifiesto de integridad abierto.", "Archivo público y firmado que liste, por mesa: identificador, hash, fecha-hora de publicación y versión. Verificación de un clic."),
        ("Exponer la fecha de publicación por mesa.", "El campo existe en el modelo interno pero no se expone en los datos abiertos; publicarlo elimina la necesidad de inferir tiempos."),
        ("Historial de versiones visible.", "Si un E-14 se republica, conservar y mostrar la versión anterior y el motivo. La trazabilidad de cambios es esencial."),
        ("Acceso abierto para auditores.", "Punto de acceso a datos sin barreras anti-automatización (CAPTCHA) para auditoría/datos abiertos, con documentación."),
        ("Consistencia de granularidad temporal.", "Marcas de tiempo más finas en la línea de resultados reducen falsos positivos como las 125 actas marcadas en este informe."),
        ("Documentar el esquema de hash.", "Aclarar qué representa el hash que nombra cada PDF (qué se hashea), para que los auditores puedan recomputarlo."),
    ]
    rdata = [[Paragraph("#", CELLB), Paragraph("Recomendación", CELLB), Paragraph("Detalle", CELLB)]]
    for i, (titulo, det) in enumerate(recs, 1):
        rdata.append([Paragraph(str(i), CELL), Paragraph("<b>" + titulo + "</b>", CELL), Paragraph(det, CELL)])
    rt = Table(rdata, colWidths=[0.8 * cm, 4.7 * cm, 10.5 * cm])
    rt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5d3e0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    s += [rt, Spacer(1, 12)]

    # 5. Veredicto
    s += [P("5. Veredicto final", H1)]
    s += [verdict_box([
        "<b>A nivel de datos y tiempos, la divulgación de la segunda vuelta presidencial 2026 se observa íntegra y consistente.</b> El resultado es claro e irreversible; las actas E-14 coinciden con lo reportado y ninguna se publicó antes del cierre de urnas. Las 125 actas marcadas corresponden a artefactos de muestreo, no a irregularidades.",
        "<b>Sin embargo, la transparencia digital es mejorable.</b> El obstáculo principal es que las actas se publican como imágenes sin metadatos: el ciudadano que descarga un E-14 no puede saber, a partir del propio archivo, cuándo fue creado o publicado, ni verificar su autenticidad de forma autónoma. Implementar metadatos, sellado de tiempo y firma digital elevaría sustancialmente la confianza pública sin cambiar el fondo del proceso.",
        "<b>En síntesis: resultado confiable; mecanismo de publicación perfectible.</b> La adopción de estándares abiertos de integridad y trazabilidad permitiría que la verificación dejara de depender de auditores técnicos y quedara al alcance de cualquier ciudadano.",
    ])]
    s += [Spacer(1, 12), rule(colors.HexColor("#c5d3e0"), 0.6)]
    s += [P("Informe elaborado a partir de información pública, con métodos reproducibles. Los artefactos de soporte (manifiestos de hashes, líneas temporales, clasificación de validez y diffs de integridad) están disponibles para su contraste.", SMALL)]

    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    print("PDF generado:", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    build()
