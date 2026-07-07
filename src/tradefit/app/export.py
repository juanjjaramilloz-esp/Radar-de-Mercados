"""Exportadores del snapshot a Excel y PDF (capa de presentación).

Funciones puras ``(ranking, meta, narrative) → bytes``: no leen disco ni red
(los datos llegan ya cargados del snapshot) y no dependen de Streamlit, así
que se testean solas. La app las conecta a botones de descarga.
"""

from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from tradefit import config
from tradefit.app.format import format_number, format_pct

#: Etiquetas de columna para los exports (subconjunto legible del ranking).
EXPORT_COLUMNS: dict[str, str] = {
    config.COL_RANK: "#",
    config.COL_COUNTRY: "ISO3",
    config.COL_COUNTRY_NAME: "Mercado",
    config.COL_MARKET_SIZE: "Importaciones prom. (USD)",
    config.COL_GROWTH: "Crecimiento (CAGR)",
    config.COL_SHARE: "Cuota del origen",
    config.COL_SHARE_TREND: "Δ cuota",
    config.COL_COMPLEMENTARITY: "Complementariedad",
    config.COL_STABILITY: "Estabilidad macro",
    config.COL_SCORE: "Score bruto",
    config.COL_FINAL_SCORE: "Score final",
}

#: Formato numérico Excel por columna del ranking.
_EXCEL_FORMATS: dict[str, str] = {
    config.COL_MARKET_SIZE: "#,##0",
    config.COL_GROWTH: "0.0%",
    config.COL_SHARE: "0.0%",
    config.COL_SHARE_TREND: "0.0%",
    config.COL_COMPLEMENTARITY: "0.00",
    config.COL_STABILITY: "0.00",
    config.COL_SCORE: "0.000",
    config.COL_FINAL_SCORE: "0.000",
}

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def _meta_line(meta: dict[str, Any]) -> str:
    """Línea de contexto del snapshot (producto, origen, fuente, años)."""
    return (
        f"Producto: {meta.get('hs_label', '')} · Origen: {meta.get('origin_iso3', '')} · "
        f"Fuente: {meta.get('source', '')} · Datos {meta.get('data_year_min', '')}–"
        f"{meta.get('data_year_max', '')} · RCA del origen: {meta.get('rca_balassa', '—')}"
    )


def ranking_to_excel(
    ranking: pd.DataFrame, meta: dict[str, Any], narrative: dict[str, Any]
) -> bytes:
    """Arma el Excel del snapshot: hojas Ranking y Narrativa.

    Args:
        ranking: DataFrame conforme a ``ranking_schema``.
        meta: metadatos del snapshot (``meta.json``).
        narrative: narrativa del snapshot (``narrative.json``; puede ser vacía).

    Returns:
        Contenido del archivo ``.xlsx`` en bytes.
    """
    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Ranking"
    sheet.append(list(EXPORT_COLUMNS.values()))
    for cell in sheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    for _, row in ranking.iterrows():
        sheet.append([row[col] if pd.notna(row[col]) else None for col in EXPORT_COLUMNS])
    for idx, col in enumerate(EXPORT_COLUMNS, start=1):
        letter = get_column_letter(idx)
        sheet.column_dimensions[letter].width = max(12, len(EXPORT_COLUMNS[col]) + 2)
        number_format = _EXCEL_FORMATS.get(col)
        if number_format:
            for cell in sheet[letter][1:]:
                cell.number_format = number_format
    sheet.freeze_panes = "A2"

    notes = workbook.create_sheet("Narrativa")
    notes.column_dimensions["A"].width = 110
    notes.append([_meta_line(meta)])
    notes.append([])
    recommendations = narrative.get("recommendations") or []
    if recommendations:
        notes.append(["Recomendación: dónde enfocarse"])
        notes["A3"].font = Font(bold=True, size=12)
        for i, rec in enumerate(recommendations, start=1):
            reasons = "; ".join(rec.get("reasons", []))
            score = format_number(float(rec.get("final_score", 0.0)), 3)
            notes.append([f"{i}. {rec.get('name')} (score final {score}): {reasons}"])
        notes.append([])
    markets = narrative.get("markets") or {}
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    for iso3 in ranking[config.COL_COUNTRY]:
        sentences = markets.get(iso3)
        if not sentences:
            continue
        header_row = notes.max_row + 1
        notes.append([f"{names.get(iso3, iso3)} ({iso3})"])
        notes[f"A{header_row}"].font = Font(bold=True)
        for sentence in sentences:
            notes.append([f"• {sentence}"])
        notes.append([])
    for row_cells in notes.iter_rows():
        for cell in row_cells:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def ranking_to_pdf(ranking: pd.DataFrame, meta: dict[str, Any], narrative: dict[str, Any]) -> bytes:
    """Arma el PDF del snapshot: título, top-3, tabla y lectura por mercado.

    Args:
        ranking: DataFrame conforme a ``ranking_schema``.
        meta: metadatos del snapshot (``meta.json``).
        narrative: narrativa del snapshot (``narrative.json``; puede ser vacía).

    Returns:
        Contenido del archivo ``.pdf`` en bytes.
    """
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=12)
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]

    story: list[Any] = [
        Paragraph("Radar de Mercados — ranking de destinos", styles["Title"]),
        Paragraph(_meta_line(meta), body),
        Spacer(1, 0.4 * cm),
    ]

    recommendations = narrative.get("recommendations") or []
    if recommendations:
        story.append(Paragraph("Recomendación: dónde enfocarse", h2))
        for i, rec in enumerate(recommendations, start=1):
            reasons = "; ".join(rec.get("reasons", []))
            score = format_number(float(rec.get("final_score", 0.0)), 3)
            story.append(
                Paragraph(
                    f"<b>{i}. {rec.get('name')}</b> (score final {score}): {reasons}",
                    body,
                )
            )
        story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Ranking", h2))
    header = ["#", "Mercado", "Import. prom. (USD M)", "CAGR", "Cuota", "Estab.", "Score final"]
    rows: list[list[str]] = [header]
    for _, row in ranking.iterrows():
        growth = row[config.COL_GROWTH]
        rows.append(
            [
                str(int(row[config.COL_RANK])),
                str(row[config.COL_COUNTRY_NAME]),
                format_number(row[config.COL_MARKET_SIZE] / 1e6),
                "s/d" if pd.isna(growth) else format_pct(float(growth)),
                format_pct(float(row[config.COL_SHARE])),
                format_number(float(row[config.COL_STABILITY]), 2),
                format_number(float(row[config.COL_FINAL_SCORE]), 3),
            ]
        )
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FA")]),
            ]
        )
    )
    story.append(table)

    markets = narrative.get("markets") or {}
    if markets:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Lectura por mercado", h2))
        names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
        for iso3 in ranking[config.COL_COUNTRY]:
            sentences = markets.get(iso3)
            if not sentences:
                continue
            story.append(Paragraph(f"{names.get(iso3, iso3)} ({iso3})", h3))
            for sentence in sentences:
                story.append(Paragraph(f"• {sentence}", body))

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title="Radar de Mercados",
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    document.build(story)
    return buffer.getvalue()
