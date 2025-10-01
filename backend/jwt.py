from __future__ import annotations

import base64
import json
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable


class PyJWTError(Exception):
    """Base error for JWT handling."""


class InvalidTokenError(PyJWTError):
    """Raised when the token structure or signature is invalid."""


class ExpiredSignatureError(InvalidTokenError):
    """Raised when the token has expired."""


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serialisable")


def _sign(message: str, secret: str, algorithm: str) -> str:
    if algorithm != "HS256":
        raise InvalidTokenError(f"Unsupported algorithm: {algorithm}")
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def encode(payload: dict[str, Any], secret: str, algorithm: str = "HS256") -> str:
    header = {"typ": "JWT", "alg": algorithm}
    header_segment = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _b64encode(
        json.dumps(payload, separators=(",", ":"), default=_json_default).encode("utf-8")
    )
    signature_segment = _sign(f"{header_segment}.{payload_segment}", secret, algorithm)
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _parse_exp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidTokenError("Invalid exp claim") from exc
    raise InvalidTokenError("Unsupported exp claim type")


def decode(token: str, secret: str, algorithms: Iterable[str] | None = None) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise InvalidTokenError("Token structure is invalid") from exc

    header_data = json.loads(_b64decode(header_segment))
    algorithm = header_data.get("alg")
    if algorithms is not None and algorithm not in set(algorithms):
        raise InvalidTokenError("Algorithm not allowed")

    expected_signature = _sign(f"{header_segment}.{payload_segment}", secret, algorithm)
    if not hmac.compare_digest(signature_segment, expected_signature):
        raise InvalidTokenError("Signature mismatch")

    payload = json.loads(_b64decode(payload_segment))
    exp = _parse_exp(payload.get("exp"))
    if exp is not None and datetime.now(timezone.utc) > exp:
        raise ExpiredSignatureError("Token has expired")
    return payload


__all__ = [
    "encode",
    "decode",
    "PyJWTError",
    "InvalidTokenError",
    "ExpiredSignatureError",
]
