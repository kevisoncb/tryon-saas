from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.paths import LOGS_DIR


def log_job(job_id: str, msg: str) -> None:
    line = f"{datetime.utcnow().isoformat()}Z | {job_id} | {msg}"
    print(line)
    try:
        (LOGS_DIR / f"{job_id}.log").open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass
