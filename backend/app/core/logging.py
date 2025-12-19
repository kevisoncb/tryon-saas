from pathlib import Path
from datetime import datetime
from settings import LOGS_DIR


def job_log(job_id: str, msg: str) -> None:
    p: Path = LOGS_DIR / f"{job_id}.log"
    ts = datetime.utcnow().isoformat()
    with p.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg.rstrip()}\n")
