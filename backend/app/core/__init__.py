from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
REDIS_URL = os.getenv("REDIS_URL", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Create backend/.env based on .env.example")
if not REDIS_URL:
    # Redis é obrigatório para fila (no trabalho você só codifica; em casa configura)
    # Deixar como erro é melhor do que rodar "meia-boca".
    raise RuntimeError("REDIS_URL not set. Create backend/.env based on .env.example")
