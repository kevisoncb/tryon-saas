# backend/app/core/logging.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from settings import LOGS_DIR


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_logs_dir() -> None:
    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)


def job_log(job_id: str, msg: str, *, extra: Optional[dict[str, Any]] = None) -> None:
    """
    Log por job em arquivo.
    Mantém compatibilidade com a assinatura atual e acrescenta opção de 'extra'.
    O seu arquivo atual grava apenas texto e não cria o diretório. :contentReference[oaicite:3]{index=3}
    """
    _ensure_logs_dir()

    p: Path = Path(LOGS_DIR) / f"{job_id}.log"
    payload = {
        "ts": _utc_iso(),
        "job_id": job_id,
        "message": (msg or "").rstrip(),
    }
    if extra:
        payload["extra"] = extra

    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
