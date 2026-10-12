"""
Build Margaret Ellis's SYNTHETIC discharge letter (one A4 page).

All names, places, dates and numbers are invented. The wording below
is the letter: tests, the demo and the extraction answer key depend on
it, so change it here only, then re-run the check:

    python scripts/letters/make_margaret_letter.py

The check reads the PDF back and confirms every line is present word
for word. Needs ReportLab (pip install reportlab); only this script
uses it.
"""

import re
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "letter1_margaret_knee_replacement_SYNTHETIC.pdf"

BANNER = "SYNTHETIC DOCUMENT. NOT A REAL PATIENT. FOR DEMO AND TESTING ONLY."
BANNER_NOTE = "All names, places and details in this letter are invented."
FOOTER = "SYNTHETIC DOCUMENT. NOT A REAL PATIENT."

HOSPITAL = "EXAMPLE GENERAL HOSPITAL (fictional)"
WARD = "Orthopaedic Ward 4"

PATIENT = [
    ("Patient:", "Margaret Ellis"),
    ("Date of birth:", "3 March 1958 (age 68)"),
    ("Patient ID:", "SYN-0001"),
    ("Admitted:", "Monday 12 October 2026"),
    ("Discharged:", "Friday 16 October 2026"),
    ("Consultant:", "Dr R. Sample, Orthopaedic Surgeon"),
]

# (heading, kind, lines): kind is "text", "numbered" or "bullets".
SECTIONS = [
    ("PROCEDURE", "text", [
        "Right total knee replacement on Monday 12 October 2026. The operation went as planned. No complications.",
    ]),
    ("MEDICINES TO TAKE AT HOME", "numbered", [
        "Paracetamol 500 mg tablets. Take 2 tablets four times a day (morning, midday, evening, bedtime) "
        "for 14 days. Take the morning dose after breakfast.",
        "Codeine 30 mg tablets. Take 1 tablet up to four times a day, only if needed for pain. Stop after 5 days.",
        "Apixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). "
        "Take the morning dose after breakfast. Continue as directed.",
        "Senna 7.5 mg tablets. Take 2 tablets at bedtime if constipated.",
    ]),
    ("DAILY ACTIVITIES", "bullets", [
        "Knee exercises from your physiotherapy sheet: three times a day (morning, afternoon, evening).",
        "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame. "
        "Times agreed with you on the ward: 7:30 am, before breakfast, and 3:00 pm.",
        "Ice pack on the knee for 20 minutes after each set of exercises.",
        "Rest with your leg raised between activities.",
    ]),
    ("DIET", "bullets", [
        "Eat plenty of fibre, such as fruit, vegetables and wholegrain bread, "
        "to help prevent constipation from your pain medicine.",
        "Drink 6 to 8 glasses of water or other fluids a day.",
        "Do not drink alcohol while you are taking codeine.",
    ]),
    ("WOUND CARE", "bullets", [
        "Keep the dressing clean and dry. Do not remove it yourself.",
        "Your wound clips will be removed on Monday 26 October 2026.",
    ]),
    ("RESTRICTIONS", "bullets", [
        "Do not drive until your consultant has reviewed you at your 6-week appointment and told you it is safe.",
        "Do not kneel on the operated knee.",
        "Do not have a bath or go swimming until the wound has healed. "
        "Showering is fine if the dressing stays dry.",
    ]),
    ("FOLLOW-UP APPOINTMENTS", "bullets", [
        "Physiotherapy: Thursday 22 October 2026, 2:00 pm, Outpatient Physiotherapy, Example General Hospital.",
        "Wound clip removal: Monday 26 October 2026, 10:30 am, practice nurse at your local surgery.",
        "Consultant review: Monday 23 November 2026, 9:15 am, Orthopaedic Clinic, Example General Hospital.",
    ]),
]

WARNING_INTRO = "Call the ward on 0000 000 000 (fictional number) if you have:"
WARNING_SIGNS = [
    "Pain, swelling, redness or heat in your calf.",
    "Redness, swelling or fluid leaking from the wound.",
    "A temperature of 38°C or higher.",
    "Pain that your medicines do not control.",
]
EMERGENCY = "Call emergency services straight away if you have chest pain or sudden shortness of breath."
SIGNED = "Signed: Dr R. Sample, Orthopaedic Surgeon"

RED = colors.HexColor("#B3264F")

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8.6, leading=10.6)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.6, leading=9.2, alignment=TA_CENTER)
HEADING = ParagraphStyle("heading", parent=BODY, fontName="Helvetica-Bold", fontSize=9.2,
                         leading=11, spaceBefore=5, spaceAfter=1.5, textColor=RED)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=15,
                       spaceBefore=3, spaceAfter=3)
HOSPITAL_STYLE = ParagraphStyle("hospital", parent=BODY, fontName="Helvetica-Bold", fontSize=10, leading=12)
BANNER_STYLE = ParagraphStyle("banner", parent=BODY, fontName="Helvetica-Bold", textColor=colors.white,
                              alignment=TA_CENTER, fontSize=8.6, leading=10.6)


def _banner(text: str) -> Table:
    table = Table([[Paragraph(text, BANNER_STYLE)]], colWidths=[180 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), RED),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _list(lines: list[str], numbered: bool) -> ListFlowable:
    items = [ListItem(Paragraph(line, BODY), leftIndent=11) for line in lines]
    if numbered:
        return ListFlowable(items, bulletType="1", bulletFormat="%s.", leftIndent=11,
                            bulletFontName="Helvetica", bulletFontSize=8.6)
    return ListFlowable(items, bulletType="bullet", start="•", leftIndent=11,
                        bulletFontName="Helvetica", bulletFontSize=8.6)


def build() -> bytes:
    story = [_banner(BANNER), Paragraph(BANNER_NOTE, SMALL), Spacer(1, 4),
             Paragraph(HOSPITAL, HOSPITAL_STYLE), Paragraph(WARD, BODY), Paragraph("DISCHARGE LETTER", TITLE)]

    details = Table(
        [[Paragraph(f"<b>{label}</b>", BODY), Paragraph(value, BODY)] for label, value in PATIENT],
        colWidths=[30 * mm, 150 * mm],
    )
    details.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(details)

    for heading, kind, lines in SECTIONS:
        story.append(Paragraph(heading, HEADING))
        if kind == "text":
            story.extend(Paragraph(line, BODY) for line in lines)
        else:
            story.append(_list(lines, numbered=kind == "numbered"))

    story += [Paragraph("WARNING SIGNS", HEADING), Paragraph(WARNING_INTRO, BODY),
              _list(WARNING_SIGNS, numbered=False), Spacer(1, 2), Paragraph(f"<b>{EMERGENCY}</b>", BODY),
              Spacer(1, 6), Paragraph(SIGNED, BODY), Spacer(1, 4), _banner(FOOTER)]

    buffer = BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=11 * mm, bottomMargin=10 * mm,
        title="SYNTHETIC discharge letter - Margaret Ellis", author="AfterWard demo (synthetic data)",
        subject="Synthetic document for demo and testing only",
    ).build(story)
    return buffer.getvalue()


def every_line() -> list[str]:
    lines = [BANNER, BANNER_NOTE, HOSPITAL, WARD, "DISCHARGE LETTER", WARNING_INTRO, EMERGENCY, SIGNED, FOOTER]
    lines += [f"{label} {value}" for label, value in PATIENT]
    for heading, _, items in SECTIONS:
        lines += [heading, *items]
    return lines + WARNING_SIGNS


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9°]+", text.lower()))


def check(pdf: bytes) -> list[str]:
    """Lines not found word for word in the PDF's text (empty means all present)."""

    reader = PdfReader(BytesIO(pdf))
    text = f" {_words(' '.join(page.extract_text() or '' for page in reader.pages))} "
    missing = [line for line in every_line() if f" {_words(line)} " not in text]
    if len(reader.pages) != 1:
        missing.append(f"<expected 1 page, got {len(reader.pages)}>")
    return missing


if __name__ == "__main__":
    pdf = build()
    missing = check(pdf)
    if missing:
        print("Not written. These lines are missing from the PDF text:")
        for line in missing:
            print("  -", line)
        sys.exit(1)
    OUTPUT.write_bytes(pdf)
    print(f"Wrote {OUTPUT.relative_to(Path.cwd()) if OUTPUT.is_relative_to(Path.cwd()) else OUTPUT}")
    print(f"Checked: all {len(every_line())} lines present word for word, 1 page.")
