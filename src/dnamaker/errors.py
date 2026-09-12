"""Errors raised by the biology adapter."""

from __future__ import annotations

from typing import Any


class BiologyError(Exception):
    """A structured biology failure that remains an ordinary exception."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        return self.message
