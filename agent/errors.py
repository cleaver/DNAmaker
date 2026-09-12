from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkflowError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "details": self.details or {}}}
