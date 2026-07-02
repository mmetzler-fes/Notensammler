"""Authentifizierung: Passwortprüfung (bcrypt oder Klartext) und JWT."""
from __future__ import annotations

import datetime as dt
import hmac
from typing import Optional

import jwt

from .config import settings

try:  # bcrypt ist optional – Klartext-Passwörter funktionieren auch ohne.
    import bcrypt
except ImportError:  # pragma: no cover
    bcrypt = None


def verify_password(stored: str, given: str) -> bool:
    """Vergleicht Passwort mit dem in der ODS hinterlegten Wert.

    Erkennt bcrypt-Hashes (``$2a$``/``$2b$``/``$2y$``) automatisch und fällt
    sonst auf einen zeitkonstanten Klartextvergleich zurück.
    """
    if stored is None:
        return False
    if stored.startswith(("$2a$", "$2b$", "$2y$")) and bcrypt is not None:
        try:
            return bcrypt.checkpw(given.encode(), stored.encode())
        except ValueError:
            return False
    return hmac.compare_digest(stored, given)


def create_token(kuerzel: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": kuerzel,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.JWT_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    """Gibt das Kürzel zurück oder None bei ungültigem/abgelaufenem Token."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
