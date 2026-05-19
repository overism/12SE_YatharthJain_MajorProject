import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESOURCES_DIR = os.path.join(DATA_DIR, "resources")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")
CHAT_DATABASE_DIR = os.path.join(BASE_DIR, "Chat_Database")

SUBJECT_RESOURCE_DIRS = {
    "Software Engineering": os.path.join(RESOURCES_DIR, "software_engineering"),
    "English Advanced": os.path.join(RESOURCES_DIR, "english_advanced"),
    "Mathematics Advanced": os.path.join(RESOURCES_DIR, "mathematics_advanced"),
    "Chemistry": os.path.join(RESOURCES_DIR, "chemistry"),
}


def _build_chat_database_subject_dirs():
    subject_dirs = {}
    if not os.path.exists(CHAT_DATABASE_DIR):
        return subject_dirs
    for entry in os.listdir(CHAT_DATABASE_DIR):
        path = os.path.join(CHAT_DATABASE_DIR, entry)
        if os.path.isdir(path):
            subject_dirs[entry] = path
    return subject_dirs


CHAT_DATABASE_SUBJECT_DIRS = _build_chat_database_subject_dirs()


def ensure_data_directories():
    os.makedirs(CHROMA_DIR, exist_ok=True)
    for folder in SUBJECT_RESOURCE_DIRS.values():
        os.makedirs(folder, exist_ok=True)
