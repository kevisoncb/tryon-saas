import os
from pathlib import Path
from config import load_env_file


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV = BASE_DIR / ".env"

# tenta carregar .env, se existir
load_env_file(str(DEFAULT_ENV))

STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RESULTS_DIR = STORAGE_DIR / "results"
LOGS_DIR = STORAGE_DIR / "logs"

for d in (STORAGE_DIR, UPLOADS_DIR, RESULTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/tryon_db",
)

API_TITLE = os.getenv("API_TITLE", "TryOn SaaS API")
API_VERSION = os.getenv("API_VERSION", "3.1.0")
