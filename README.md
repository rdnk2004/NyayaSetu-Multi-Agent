# Day 1 - Retrieval Pipeline

## Setup (run once)

```bash
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run the pipeline (3 steps, in order)

```bash
python3 src/chunk_text.py         # raw text -> data/processed/chunks.json
python3 src/embed_and_store.py    # chunks -> embeddings -> Chroma vector store
python3 src/retrieve.py           # runs 5 sanity-check queries
```

The first time you run `embed_and_store.py` it downloads the embedding
model (~90MB) from huggingface.co - needs internet, only happens once.

## What each file does

- `src/chunk_text.py` - parses section-tagged raw text into clean,
  metadata-tagged chunks (source act, section number, date).
- `src/embed_and_store.py` - turns chunks into embeddings and loads
  them into a local Chroma vector database.
- `src/retrieve.py` - the actual retrieval function every later agent
  will call: query in, top-k relevant chunks out.

## Today's task

1. Replace `data/raw/consumer_protection_sample.txt` with real,
   larger chunked text once your teammate hands off the full corpus
   for both domains (same SOURCE_ACT / SECTION / TITLE / TEXT format).
2. Re-run all three steps.
3. Run the formal Day 1-2 gate test: 10 real legal queries, check that
   the correct section comes back every time. Log results in the
   tracker (Day-by-Day Plan sheet).

## Adding your teammate's data

Drop their cleaned .txt files into `data/raw/` using the same format
as the sample file (SOURCE_ACT / AS_OF_DATE header, then SECTION /
TITLE / TEXT blocks). The chunker picks up every .txt file in that
folder automatically.
