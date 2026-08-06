"""
Extracts text directly from a digital PDF (no OCR needed - the India
Code PDFs have selectable text) and splits it into sections matching
the SOURCE_ACT / SECTION / TITLE / TEXT format that chunk_text.py
expects.

Usage:
    python3 extract_pdf.py path/to/Consumer-Protection-Act-2019.pdf
"""

import re
import sys
from pathlib import Path

import fitz  # pymupdf


def extract_full_text(pdf_path: str) -> str:
    """Pull all text out of the PDF, page by page, in reading order."""
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    return full_text


def split_into_sections(full_text: str) -> list[dict]:
    """
    Split the act's body text into sections using the numbering pattern
    India Code acts use, e.g.:
        2. Definitions.—In this Act...
        34. Jurisdiction of District Commission.—(1) Subject to...

    This is a starting heuristic, not perfect - always spot-check the
    output against the source PDF before trusting it fully.
    """
    # Matches: start of line, section number, period, title text, em-dash
    pattern = re.compile(
        r"\n(\d{1,3})\.\s+([A-Z].{3,150}?)\.\s*\u2014",
        re.DOTALL,
    )

    matches = list(pattern.finditer(full_text))
    sections = []

    for i, m in enumerate(matches):
        section_num = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        body = re.sub(r"\s+", " ", body)  # collapse newlines/whitespace

        if len(body) < 20:  # skip false-positive matches (e.g. table of contents entries)
            continue

        sections.append({"section": section_num, "title": title, "text": body})

    return sections


def write_output(sections: list[dict], source_act: str, as_of_date: str, out_path: str):
    lines = [f"SOURCE_ACT: {source_act}", f"AS_OF_DATE: {as_of_date}", ""]
    for sec in sections:
        lines.append(f"SECTION: {sec['section']}")
        lines.append(f"TITLE: {sec['title']}")
        lines.append(f"TEXT: {sec['text']}")
        lines.append("")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 extract_pdf.py path/to/act.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    full_text = extract_full_text(pdf_path)
    sections = split_into_sections(full_text)

    out_path = Path(pdf_path).stem.lower().replace(" ", "_") + "_sections.txt"
    write_output(
        sections,
        source_act="Consumer Protection Act, 2019",
        as_of_date="2026-08-06",
        out_path=out_path,
    )

    print(f"Extracted {len(sections)} sections -> {out_path}")
    print("\nSpot-check the first 3 sections:")
    for sec in sections[:3]:
        print(f"  Section {sec['section']}: {sec['title'][:60]}")
