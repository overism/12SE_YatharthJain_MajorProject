import os

from dotenv import load_dotenv

from .embedder import embed_chunks, reset_knowledge_base
from .ingestion import chunk_text, clean_text, ingest_folder
from .paths import SUBJECT_RESOURCE_DIRS, CHAT_DATABASE_SUBJECT_DIRS, ensure_data_directories


def run_full_ingestion():
    """Ingest local resources and Chat_Database into ChromaDB."""
    load_dotenv()
    ensure_data_directories()

    print("=" * 50)
    print("HSC KNOWLEDGE BASE INGESTION")
    print("=" * 50)
    reset_knowledge_base()

    totals = {}
    for subject, folder_path in SUBJECT_RESOURCE_DIRS.items():
        print(f"\nProcessing: {subject}")
        all_chunks = []

        print(f"  Ingesting local files from {folder_path}")
        local_chunks = ingest_folder(folder_path, subject) if os.path.exists(folder_path) else []
        all_chunks.extend(local_chunks)
        print(f"  {len(local_chunks)} chunks from local files")

        chat_db_path = CHAT_DATABASE_SUBJECT_DIRS.get(subject)
        if chat_db_path:
            print(f"  Ingesting Chat_Database files from {chat_db_path}")
            chat_chunks = ingest_folder(chat_db_path, subject, source_type="chat_db")
            all_chunks.extend(chat_chunks)
            print(f"  {len(chat_chunks)} chunks from Chat_Database")

        if all_chunks:
            print(f"  Embedding {len(all_chunks)} total chunks")
            embed_chunks(all_chunks)

        totals[subject] = len(all_chunks)
        print(f"  Complete: {len(all_chunks)} chunks stored")

    for subject, folder_path in CHAT_DATABASE_SUBJECT_DIRS.items():
        if subject in SUBJECT_RESOURCE_DIRS:
            continue

        print(f"\nProcessing Chat_Database-only subject: {subject}")
        all_chunks = []
        print(f"  Ingesting Chat_Database files from {folder_path}")
        chat_chunks = ingest_folder(folder_path, subject, source_type="chat_db")
        all_chunks.extend(chat_chunks)
        print(f"  {len(chat_chunks)} chunks from Chat_Database")

        if all_chunks:
            print(f"  Embedding {len(all_chunks)} total chunks")
            embed_chunks(all_chunks)

        totals[subject] = len(all_chunks)
        print(f"  Complete: {len(all_chunks)} chunks stored")

    print("\n" + "=" * 50)
    print("INGESTION COMPLETE")
    print("Source: local resources + Chat_Database only")
    print("=" * 50)
    return totals


if __name__ == "__main__":
    run_full_ingestion()
