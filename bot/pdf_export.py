"""Render a vacancy as a standalone PDF -- a "printout" of the job ad
alongside its generated ansøgning, e.g. for jobcenter/kommune reporting
that expects proof of what was actually applied to.
"""

import re
from pathlib import Path

from fpdf import FPDF

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
REGULAR_FONT = FONTS_DIR / "DejaVuSans.ttf"
BOLD_FONT = FONTS_DIR / "DejaVuSans-Bold.ttf"


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def vacancy_to_pdf(vacancy, output_path: str, contact=None):
    pdf = FPDF()
    pdf.add_font("DejaVu", "", str(REGULAR_FONT))
    pdf.add_font("DejaVu", "B", str(BOLD_FONT))
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    if contact is not None:
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("DejaVu", "B", 12)
        pdf.multi_cell(0, 7, "Для лога / отчётности — сводка", fill=True)
        pdf.set_font("DejaVu", "", 11)
        summary_lines = [
            ("Вакансия", vacancy.title),
            ("Компания", vacancy.company),
            ("Контактное лицо", contact.name),
            ("Телефон", contact.phone),
            ("Email", contact.email),
            ("Ссылка", vacancy.url),
        ]
        for label, value in summary_lines:
            pdf.set_font("DejaVu", "B", 11)
            pdf.write(6, f"{label}: ")
            pdf.set_font("DejaVu", "", 11)
            pdf.write(6, value or "")
            pdf.ln(7)
        pdf.ln(6)

    pdf.set_font("DejaVu", "B", 14)
    pdf.multi_cell(0, 8, vacancy.title)
    pdf.ln(2)

    pdf.set_font("DejaVu", "", 11)
    meta_lines = [
        ("Компания", vacancy.company),
        ("Место", vacancy.location),
        ("Источник", vacancy.source),
        ("Ссылка", vacancy.url),
    ]
    for label, value in meta_lines:
        if not value:
            continue
        pdf.set_font("DejaVu", "B", 11)
        pdf.write(6, f"{label}: ")
        pdf.set_font("DejaVu", "", 11)
        pdf.write(6, value)
        pdf.ln(7)

    pdf.ln(4)
    pdf.set_font("DejaVu", "B", 12)
    pdf.multi_cell(0, 7, "Описание вакансии")
    pdf.ln(1)

    pdf.set_font("DejaVu", "", 10.5)
    pdf.multi_cell(0, 6, _strip_html(vacancy.description) or "(нет текста описания)")

    pdf.output(output_path)
    return output_path


def letter_to_pdf(letter_text: str, vacancy, output_path: str):
    pdf = FPDF()
    pdf.add_font("DejaVu", "", str(REGULAR_FONT))
    pdf.add_font("DejaVu", "B", str(BOLD_FONT))
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    pdf.set_font("DejaVu", "B", 13)
    pdf.multi_cell(0, 7, f"Ansøgning — {vacancy.title}")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, vacancy.company)
    pdf.ln(6)

    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", 11)
    pdf.multi_cell(0, 6, letter_text)

    pdf.output(output_path)
    return output_path
