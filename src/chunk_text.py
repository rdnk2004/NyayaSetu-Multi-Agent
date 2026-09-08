"""
Day 1 - Step 1: Chunking

Takes raw legal text (already section-tagged) and turns it into a list of
chunks, each with metadata attached: source act, section number, and a
date-stamp. This metadata is what lets the Citation Verification Agent
later confirm a claim actually traces back to a real, dated section.

Expected input file format (see data/raw/consumer_protection_sample.txt):

    SOURCE_ACT: <act name>
    AS_OF_DATE: <date>

    SECTION: <section number>
    TITLE: <short title>
    TEXT: <the actual provision text>

    SECTION: <next section number>
    ...
"""

import re
import json
from pathlib import Path


def parse_sections(raw_text: str) -> list[dict]:
    """Parse a section-tagged text file into a list of section dicts."""
    lines = raw_text.strip().split("\n")

    source_act = ""
    as_of_date = ""
    sections = []
    current = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("SOURCE_ACT:"):
            source_act = line.split(":", 1)[1].strip()
        elif line.startswith("AS_OF_DATE:"):
            as_of_date = line.split(":", 1)[1].strip()
        elif line.startswith("SECTION:"):
            if current:
                sections.append(current)
            current = {
                "section": line.split(":", 1)[1].strip(),
                "title": "",
                "text": "",
                "source_act": source_act,
                "as_of_date": as_of_date,
            }
        elif line.startswith("TITLE:") and current:
            current["title"] = line.split(":", 1)[1].strip()
        elif line.startswith("TEXT:") and current:
            current["text"] = line.split(":", 1)[1].strip()

    if current:
        sections.append(current)

    return sections


def split_on_enumeration(text: str) -> list[tuple[str, str]]:
    """
    Try to split text on top-level numbered sub-clauses like (1), (2), (3).
    Returns a list of (clause_label, clause_text) tuples. Clause_label is
    "" if no enumeration was found (caller should fall back to word-count
    splitting in that case).

    This matters a lot for sections like "Definitions" that cram dozens
    of distinct legal items into one block - splitting on structure keeps
    each definition intact and separately citable (e.g. Section 2(11)),
    instead of chopping it at an arbitrary word count.
    """
    # Matches "(1) " / "(23) " etc. at a clause boundary - requires the
    # number to be followed by a capital letter or a quote mark, which is
    # how definitions/subsections actually start (avoids false-splitting
    # on stray parenthetical numbers elsewhere in the text).
    pattern = re.compile(r'\((\d{1,3})\)\s+(?=[“"\'A-Z])')
    matches = list(pattern.finditer(text))

    # Need at least 3 matches to trust this is a real enumerated block,
    # not a one-off parenthetical reference.
    if len(matches) < 3:
        return [("", text)]

    pieces = []
    for i, m in enumerate(matches):
        clause_num = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clause_text = text[start:end].strip()
        if clause_text:
            pieces.append((clause_num, clause_text))
    return pieces


def chunk_sections(sections: list[dict], max_words: int = 350) -> list[dict]:
    """
    Turn parsed sections into retrieval chunks.

    Preference order:
      1. If a section has a numbered sub-clause structure (e.g. Definitions
         with (1), (2), (3)...), split on that structure - each clause
         becomes its own chunk, tagged e.g. section "2(11)". This keeps
         legal claims atomic and precisely citable.
      2. Otherwise, if the section is short enough, keep it as one chunk.
      3. Otherwise (long section, no clear enumeration), fall back to
         sentence-boundary splitting by word count.
    """
    chunks = []
    chunk_id = 0

    for sec in sections:
        enum_pieces = split_on_enumeration(sec["text"])
        has_enumeration = enum_pieces[0][0] != ""

        if has_enumeration:
            final_pieces = []
            for clause_num, clause_text in enum_pieces:
                clause_words = clause_text.split()
                if len(clause_words) <= max_words:
                    final_pieces.append((clause_num, clause_text))
                else:
                    # a single clause is still too long - sentence-split it
                    sentences = re.split(r"(?<=[.;])\s+", clause_text)
                    piece, buf, buf_len = [], [], 0
                    for s in sentences:
                        s_len = len(s.split())
                        if buf_len + s_len > max_words and buf:
                            final_pieces.append((clause_num, " ".join(buf)))
                            buf, buf_len = [], 0
                        buf.append(s)
                        buf_len += s_len
                    if buf:
                        final_pieces.append((clause_num, " ".join(buf)))

            for clause_num, clause_text in final_pieces:
                chunk_id += 1
                chunks.append({
                    "id": f"chunk_{chunk_id:04d}",
                    "text": clause_text,
                    "source_act": sec["source_act"],
                    "section": f"{sec['section']}({clause_num})",
                    "title": sec["title"],
                    "as_of_date": sec["as_of_date"],
                    "part": "1/1",
                })
            continue

        words = sec["text"].split()

        if len(words) <= max_words:
            pieces = [sec["text"]]
        else:
            # Split long sections on sentence boundaries into ~max_words pieces
            sentences = re.split(r"(?<=[.;])\s+", sec["text"])
            pieces, current_piece, current_len = [], [], 0
            for s in sentences:
                s_len = len(s.split())
                if current_len + s_len > max_words and current_piece:
                    pieces.append(" ".join(current_piece))
                    current_piece, current_len = [], 0
                current_piece.append(s)
                current_len += s_len
            if current_piece:
                pieces.append(" ".join(current_piece))

        for i, piece in enumerate(pieces):
            chunk_id += 1
            chunks.append({
                "id": f"chunk_{chunk_id:04d}",
                "text": piece,
                "source_act": sec["source_act"],
                "section": sec["section"],
                "title": sec["title"],
                "as_of_date": sec["as_of_date"],
                "part": f"{i+1}/{len(pieces)}" if len(pieces) > 1 else "1/1",
            })

    return chunks


def parse_case_law(raw_text: str) -> dict:
    """Parse a structured case law file into a case dict."""
    lines = raw_text.strip().split("\n")
    case = {
        "case_title": "",
        "court": "",
        "date": "",
        "source_url": "",
        "attribution": "",
        "reasoning": "",
    }
    in_reasoning = False
    reasoning_lines = []

    for line in lines:
        if in_reasoning:
            reasoning_lines.append(line)
            continue
        line_s = line.strip()
        if line_s.startswith("CASE_TITLE:"):
            case["case_title"] = line_s.split(":", 1)[1].strip()
        elif line_s.startswith("COURT:"):
            case["court"] = line_s.split(":", 1)[1].strip()
        elif line_s.startswith("DATE:"):
            case["date"] = line_s.split(":", 1)[1].strip()
        elif line_s.startswith("SOURCE_URL:"):
            case["source_url"] = line_s.split(":", 1)[1].strip()
        elif line_s.startswith("ATTRIBUTION:"):
            case["attribution"] = line_s.split(":", 1)[1].strip()
        elif line_s.startswith("REASONING:"):
            in_reasoning = True
            remainder = line_s.split(":", 1)[1].strip()
            if remainder:
                reasoning_lines.append(remainder)

    case["reasoning"] = "\n".join(reasoning_lines).strip()
    return case


def chunk_case_law(case: dict, max_words: int = 350) -> list[dict]:
    """Turn a case law record into retrieval chunks."""
    text = case.get("reasoning", "")
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces = []
    current_piece, current_len = [], 0

    for para in paragraphs:
        p_len = len(para.split())
        if current_len + p_len > max_words and current_piece:
            pieces.append("\n\n".join(current_piece))
            current_piece, current_len = [], 0
        current_piece.append(para)
        current_len += p_len

    if current_piece:
        pieces.append("\n\n".join(current_piece))

    safe_title = re.sub(r"[^a-zA-Z0-9]", "_", case.get("case_title", "case"))[:30].strip("_")
    chunks = []
    for i, piece in enumerate(pieces):
        chunks.append({
            "id": f"case_{safe_title}_{i+1:02d}",
            "text": piece,
            "source_act": f"Precedent ({case.get('court', 'Court')})",
            "section": case.get("case_title", "Precedent Case"),
            "title": case.get("case_title", ""),
            "as_of_date": case.get("date", ""),
            "source_url": case.get("source_url", ""),
            "doc_type": "case_law",
            "part": f"{i+1}/{len(pieces)}" if len(pieces) > 1 else "1/1",
        })
    return chunks


if __name__ == "__main__":
    raw_dir = Path(__file__).parent.parent / "data" / "raw"
    case_law_dir = raw_dir / "case_law"
    processed_dir = Path(__file__).parent.parent / "data" / "processed"
    processed_dir.mkdir(exist_ok=True)

    all_chunks = []
    # 1. Parse statutory sections
    for raw_file in raw_dir.glob("*.txt"):
        raw_text = raw_file.read_text(encoding="utf-8")
        sections = parse_sections(raw_text)
        chunks = chunk_sections(sections)
        all_chunks.extend(chunks)
        print(f"[Statute] {raw_file.name}: {len(sections)} sections -> {len(chunks)} chunks")

    # 2. Parse precedent case law
    if case_law_dir.exists():
        case_files = list(case_law_dir.glob("*.txt"))
        case_chunks_count = 0
        for case_file in case_files:
            case_text = case_file.read_text(encoding="utf-8")
            case_data = parse_case_law(case_text)
            c_chunks = chunk_case_law(case_data)
            all_chunks.extend(c_chunks)
            case_chunks_count += len(c_chunks)
        print(f"[Case Law] {len(case_files)} cases -> {case_chunks_count} chunks")

    out_path = processed_dir / "chunks.json"
    out_path.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")
    print(f"\nSaved {len(all_chunks)} total chunks to {out_path}")
