"""Placeholder for code that is yours to write. Calling it answers HTTP 501 'Not Implemented';
Mission Control and the UI show that as "not built yet" instead of an error."""

from typing import NoReturn

from fastapi import HTTPException


def todo(milestone: str, what: str) -> NoReturn:
    raise HTTPException(status_code=501, detail=f"[{milestone}] TODO: {what}")
