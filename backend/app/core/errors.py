from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AppError(Exception):
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    http_status: int = 400

    def to_dict(self) -> Dict[str, Any]:
        payload = {"error_code": self.error_code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload
