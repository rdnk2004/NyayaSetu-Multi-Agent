"""
Index Case Law: Embed case law reasoning and load into a vector store

Reads data/raw/case_law/*.txt and:
  1. Parses case metadata (CASE_TITLE, COURT, DATE, SOURCE_URL, ATTRIBUTION)
     and multi-paragraph REASONING text.
  2. Embeds each case's REASONING text using multi-qa-mpnet-base-dot-v1.
  3. Stores the embedding + text + metadata in a dedicated Chroma collection
     ('case_law') using inner-product distance (hnsw:space: ip).
"""

from pathlib import Path

# pyrefly: ignore [missing-import]
import chromadb
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer

CASE_LAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "case_law"
DB_PATH = Path(__file__).parent.parent / "data" / "chroma_db"

EMBEDDING_MODEL = "multi-qa-mpnet-base-dot-v1"
COLLECTION_NAME = "case_law"


def parse_case_file(file_path: Path) -> dict:
    """Parse a single case law .txt file into metadata fields and reasoning text."""
    text = file_path.read_text(encoding="utf-8")

    fields = {
        "case_title": "",
        "court": "",
        "date": "",
        "source_url": "",
        "attribution": "",
        "reasoning": "",
    }
    field_prefixes = {
        "CASE_TITLE:": "case_title",
        "COURT:": "court",
        "DATE:": "date",
        "SOURCE_URL:": "source_url",
        "ATTRIBUTION:": "attribution",
        "REASONING:": "reasoning",
    }

    current_field = None
    accumulated = {k: [] for k in fields}

    for line in text.splitlines():
        matched_prefix = None
        for prefix in field_prefixes:
            if line.startswith(prefix):
                matched_prefix = prefix
                break

        if matched_prefix:
            current_field = field_prefixes[matched_prefix]
            content = line[len(matched_prefix):].strip()
            if content:
                accumulated[current_field].append(content)
        elif current_field is not None:
            accumulated[current_field].append(line)

    parsed = {k: "\n".join(accumulated[k]).strip() for k in fields}
    parsed["id"] = file_path.stem
    return parsed


def index_case_law(case_law_dir: Path = CASE_LAW_DIR, db_path: Path = DB_PATH):
    """Parse, embed, and store all case law files into the 'case_law' Chroma collection."""
    case_files = sorted([f for f in case_law_dir.glob("*.txt") if f.is_file()])
    if not case_files:
        print(f"No case law files found in {case_law_dir}")
        return

    cases = [parse_case_file(f) for f in case_files]
    print(f"Parsed {len(cases)} case law files from {case_law_dir}")

    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=str(db_path))

    # Recreate the collection fresh on each index run
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "ip"})

    texts = [c["reasoning"] for c in cases]
    ids = [c["id"] for c in cases]
    metadatas = [
        {
            "case_title": c["case_title"],
            "court": c["court"],
            "date": c["date"],
            "source_url": c["source_url"],
            "attribution": c["attribution"],
        }
        for c in cases
    ]

    print("Generating embeddings for case law reasoning...")
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    print(f"Indexed {len(cases)} cases into Chroma collection '{COLLECTION_NAME}' at {db_path}")
    print(f"Collection count after indexing: {collection.count()}")


if __name__ == "__main__":
    index_case_law()
