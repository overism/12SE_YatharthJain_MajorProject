"""
RAG/warmup.py
=============
Pre-loads the sentence-transformer model and ChromaDB collection
in a background daemon thread so the FIRST chat message responds
at the same speed as subsequent ones.

USAGE — add these two lines near the bottom of app.py,
        after `ensure_runtime_schema()` and before `if __name__ == '__main__':`:

    from RAG.warmup import warm_rag_on_startup
    warm_rag_on_startup()

That's it.  The thread is daemonic, so it never blocks Flask startup
or gunicorn worker booting, and it dies cleanly when the process exits.
"""

from __future__ import annotations
import sys
import threading


def warm_rag_on_startup() -> None:
    """Start a background thread to pre-load the RAG stack."""

    # Skip during test collection to avoid side-effects
    if 'pytest' in sys.modules:
        return

    def _warm() -> None:
        try:
            print('[WARMUP] Loading sentence-transformer model…', flush=True)
            from RAG.embedder import get_model, get_or_create_collection
            model      = get_model()          # downloads weights if needed (~80 MB first run)
            collection = get_or_create_collection()
            count      = collection.count()
            print(
                f'[WARMUP] Ready. Model: {model.__class__.__name__}  '
                f'| ChromaDB chunks: {count}',
                flush=True,
            )
        except Exception as exc:
            # Non-fatal — the app still works, just the first query will be slow
            print(f'[WARMUP] Pre-load failed (non-fatal): {exc}', flush=True)

    thread = threading.Thread(target=_warm, name='rag-warmup', daemon=True)
    thread.start()
