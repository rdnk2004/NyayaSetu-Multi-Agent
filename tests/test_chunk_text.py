"""
Regression tests for chunk_text.py.

Guards against case law / precedent documents ever being merged
back into the statute chunking path.
"""

import sys
from pathlib import Path

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from chunk_text import parse_sections, chunk_sections


def test_statute_chunking_on_data_raw_contains_no_case_law():
    """
    Regression test:
    Running chunk_text.py's parsing on data/raw/ must never produce chunks
    with doc_type == 'case_law' or source_act starting with 'Precedent'.
    This guards against case law ever being merged back into the statute chunking path.
    """
    repo_root = Path(__file__).resolve().parent.parent
    raw_dir = repo_root / "data" / "raw"

    statute_files = list(raw_dir.glob("*.txt"))
    assert len(statute_files) > 0, f"Expected at least one statute file in {raw_dir}"

    all_chunks = []
    for raw_file in statute_files:
        raw_text = raw_file.read_text(encoding="utf-8")
        sections = parse_sections(raw_text)
        chunks = chunk_sections(sections)
        all_chunks.extend(chunks)

    assert len(all_chunks) > 0, "Expected parsed chunks from data/raw/"

    for chunk in all_chunks:
        assert chunk.get("doc_type") != "case_law", (
            f"Chunk {chunk.get('id')} has forbidden doc_type 'case_law': {chunk}"
        )
        source_act = str(chunk.get("source_act", "") or "")
        assert not source_act.startswith("Precedent"), (
            f"Chunk {chunk.get('id')} has forbidden source_act starting with 'Precedent': {source_act}"
        )


if __name__ == "__main__":
    test_statute_chunking_on_data_raw_contains_no_case_law()
    print("test_chunk_text.py passed successfully!")
