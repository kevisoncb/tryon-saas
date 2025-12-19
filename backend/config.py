import os
from pathlib import Path


def load_env_file(path: str) -> None:
    """
    Loader simples de .env (sem depender de lib).
    - Ignora comentários e linhas vazias
    - Não sobrescreve variáveis já existentes no ambiente
    """
    p = Path(path)
    if not p.exists():
        return

    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v
