"""
RAG/retriever.py  –  Dusty knowledge retrieval

Replaces the original file. Backwards-compatible: all three functions
(retrieve, format_chunks_for_prompt, format_source_payload) are exported
so both the old and new app.py import lines work without changes.
"""

from __future__ import annotations
import traceback

from .embedder import get_model, get_or_create_collection

# ── SUBJECT ALIASES ───────────────────────────────────────────────
SUBJECT_ALIASES: dict[str, str] = {
    "Mathematics":       "Mathematics Advanced",
    "Maths":             "Mathematics Advanced",
    "Math":              "Mathematics Advanced",
    "English":           "English Advanced",
    "Science":           "Chemistry",
    "Software":          "Software Engineering",
    "SDD":               "Software Engineering",
    "Software Design":   "Software Engineering",
}

# Minimum cosine similarity (1 - distance) to include a chunk
RELEVANCE_THRESHOLD = 0.20


def normalise_subject(subject: str | None) -> str:
    if not subject:
        return "General"
    s = subject.strip()
    return SUBJECT_ALIASES.get(s, s)


def retrieve(
    question: str,
    subject:  str | None = None,
    n_results: int = 5,
) -> list[dict]:
    """
    Retrieve the top-N relevant chunks for a question.

    Always returns a list (empty on failure) — never raises,
    so callers can always fall back to general knowledge.
    """
    try:
        model      = get_model()
        collection = get_or_create_collection()

        if collection.count() == 0:
            return []

        embedding  = model.encode(question).tolist()
        norm_subj  = normalise_subject(subject)

        query_params: dict = {
            "query_embeddings": [embedding],
            "n_results":        min(n_results, collection.count()),
            "include":          ["documents", "metadatas", "distances"],
        }

        if norm_subj and norm_subj != "General":
            query_params["where"] = {"subject": norm_subj}

        results = collection.query(**query_params)

        chunks: list[dict] = []
        if not results or not results.get("documents"):
            return chunks

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            relevance = round(1.0 - float(dist), 3)
            if relevance < RELEVANCE_THRESHOLD:
                continue
            chunks.append({
                "content":     doc,
                "subject":     meta.get("subject",     ""),
                "module":      meta.get("module",      "General"),
                "source":      meta.get("source",      ""),
                "source_type": meta.get("source_type", "local"),
                "url_or_path": meta.get("url_or_path", ""),
                "relevance":   relevance,
            })

        chunks.sort(key=lambda c: c["relevance"], reverse=True)
        return chunks

    except Exception as exc:
        print(f"[RETRIEVER] Retrieval error: {exc}")
        traceback.print_exc()
        return []


def format_chunks_for_prompt(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into the source block injected into prompts.
    Returns a fallback string when nothing was retrieved.
    """
    if not chunks:
        return (
            "No specific resources were found in the knowledge base for this query. "
            "Answer from your general HSC knowledge and note that no source was retrieved."
        )

    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        subj = chunk.get("subject",   "HSC")
        mod  = chunk.get("module",    "General")
        src  = chunk.get("source",    "Unknown")
        rel  = chunk.get("relevance", 0)
        parts.append(
            f"[Source {i} | {subj} — {mod} — {src} | relevance {rel:.0%}]\n"
            f"{chunk['content']}"
        )

    return "\n\n---\n\n".join(parts)


def format_source_payload(chunks: list[dict]) -> list[dict]:
    """
    Produce a deduplicated, frontend-ready source list (max 6 entries).
    Used by app.py chat routes to populate the Sources panel.
    """
    seen:    set[tuple] = set()
    payload: list[dict] = []

    for chunk in chunks:
        subj = chunk.get("subject", "HSC")
        mod  = chunk.get("module",  "General")
        src  = chunk.get("source",  "Source")
        key  = (subj, mod, src)

        if key in seen:
            continue
        seen.add(key)

        payload.append({
            "label":       f"{subj} — {src}",
            "subject":     subj,
            "module":      mod,
            "source":      src,
            "source_type": chunk.get("source_type", ""),
            "url_or_path": chunk.get("url_or_path", ""),
            "relevance":   chunk.get("relevance",   0),
        })

    return payload[:6]