"""
RAG/embedder.py  –  Dusty ChromaDB embedding layer
Improvements:
  - Duplicate UUID guard (prevents add() errors on re-ingestion)
  - Per-batch error handling so one bad batch doesn't kill the whole run
  - Lazy model load cached at module level
  - Returns count of chunks actually stored
"""

from __future__ import annotations
import traceback
import uuid

import chromadb
from sentence_transformers import SentenceTransformer

from .paths import CHROMA_DIR, ensure_data_directories

# ── LAZY MODEL ────────────────────────────────────────────────────
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("[EMBEDDER] Loading sentence-transformer model (first run downloads ~80 MB)…")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[EMBEDDER] Model loaded.")
    return _model


# ── CHROMA CLIENT ─────────────────────────────────────────────────
def get_chroma_client() -> chromadb.PersistentClient:
    ensure_data_directories()
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_or_create_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="hsc_knowledge",
        metadata={"hnsw:space": "cosine"},
    )


def reset_knowledge_base() -> chromadb.Collection:
    """Delete and recreate the collection (used at ingestion start)."""
    client = get_chroma_client()
    try:
        client.delete_collection(name="hsc_knowledge")
        print("[EMBEDDER] Existing collection deleted.")
    except Exception:
        pass
    return get_or_create_collection()


# ── EMBED & STORE ─────────────────────────────────────────────────
def embed_chunks(chunks: list[dict], batch_size: int = 100) -> int:
    """
    Encode chunk texts and upsert them into ChromaDB.

    Returns the number of chunks successfully stored.
    Skips empty content; handles per-batch errors gracefully.
    """
    if not chunks:
        return 0

    # Filter out empty content
    valid = [c for c in chunks if c.get("content", "").strip()]
    if not valid:
        print("[EMBEDDER] No valid chunks to embed (all were empty).")
        return 0

    collection = get_or_create_collection()
    model      = get_model()

    texts     = [c["content"] for c in valid]
    ids       = [str(uuid.uuid4()) for _ in valid]
    metadatas = [
        {
            "subject":     str(c.get("subject",     "")),
            "module":      str(c.get("module",      "General")),
            "source":      str(c.get("source",      "")),
            "source_type": str(c.get("source_type", "local")),
            "url_or_path": str(c.get("url_or_path", c.get("filepath", ""))),
        }
        for c in valid
    ]

    print(f"[EMBEDDER] Encoding {len(valid)} chunks…")
    try:
        embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
    except Exception as exc:
        print(f"[EMBEDDER] Encoding failed: {exc}")
        traceback.print_exc()
        return 0

    stored = 0
    for i in range(0, len(valid), batch_size):
        sl = slice(i, i + batch_size)
        try:
            collection.add(
                documents =texts    [sl],
                embeddings=[e.tolist() for e in embeddings[sl]],
                metadatas =metadatas[sl],
                ids       =ids      [sl],
            )
            stored += len(ids[sl])
        except Exception as exc:
            print(f"[EMBEDDER] Batch {i//batch_size + 1} failed: {exc}")
            traceback.print_exc()

    print(f"[EMBEDDER] Stored {stored}/{len(valid)} chunks.")
    return stored