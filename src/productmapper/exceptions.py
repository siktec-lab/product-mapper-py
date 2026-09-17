"""Exceptions raised by the ProductMapper client.

Every failure is a :class:`ProductMapperError`, so a single ``except`` can handle all of
them, while the subclasses let you react to specific conditions such as an exhausted
credit balance or a rate limit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "AuthenticationError",
    "ConnectionError",
    "CreditsExhaustedError",
    "JobFailedError",
    "NotFoundError",
    "PermissionError",
    "ProductMapperError",
    "RateLimitError",
    "ServerError",
    "TimeoutError",
    "ValidationError",
    "error_from_response",
]


class ProductMapperError(Exception):
    """Base class for every error this client raises."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        body: Any = None,
        request: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        #: HTTP status, when the failure came from a response.
        self.status = status
        #: Machine-readable code from the API, for example ``CREDITS_EXHAUSTED``.
        self.code = code
        #: Parsed response body, when there was one.
        self.body = body
        #: The request that failed, as method and path.
        self.request = request

    def __str__(self) -> str:
        if self.status is not None:
            return f"[{self.status}] {self.message}"
        return self.message


class ValidationError(ProductMapperError):
    """400, or the client rejected the arguments before sending anything."""


class AuthenticationError(ProductMapperError):
    """401. The API key is missing, malformed or revoked."""


class PermissionError(ProductMapperError):
    """403 without a credits code. Usually no active organization is selected."""


class CreditsExhaustedError(ProductMapperError):
    """403 with code ``CREDITS_EXHAUSTED``. Top up or upgrade to continue."""


class NotFoundError(ProductMapperError):
    """404. No match in the Amazon catalog, or the resource is not yours."""


class RateLimitError(ProductMapperError):
    """429. The organization exceeded its plan requests-per-minute ceiling."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        body: Any = None,
        request: str | None = None,
        retry_after: float | None = None,
        limit: int | None = None,
        remaining: int | None = None,
    ) -> None:
        super().__init__(message, status=status, code=code, body=body, request=request)
        #: Seconds to wait before retrying, from the Retry-After header.
        self.retry_after = retry_after
        #: Requests per minute allowed on the current plan.
        self.limit = limit
        #: Requests left in the current window.
        self.remaining = remaining


class ServerError(ProductMapperError):
    """5xx. The API failed to handle an otherwise valid request."""


class TimeoutError(ProductMapperError):
    """The request, or a polling loop, exceeded its allotted time."""


class ConnectionError(ProductMapperError):
    """The request never reached the API: DNS, TLS, connection reset, offline."""


class JobFailedError(ProductMapperError):
    """A queued lookup or batch job finished in a failed state."""

    def __init__(self, message: str, *, job_id: str | None = None, body: Any = None) -> None:
        super().__init__(message, body=body)
        #: The job id that failed.
        self.job_id = job_id


def _numeric_header(headers: Mapping[str, str] | None, name: str) -> float | None:
    if not headers:
        return None
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def error_from_response(
    status: int,
    body: Any,
    request: str,
    headers: Mapping[str, str] | None = None,
) -> ProductMapperError:
    """Build the right exception subclass for a failed response."""
    payload = body if isinstance(body, dict) else {}
    code = payload.get("code") if isinstance(payload.get("code"), str) else None
    raw_message = payload.get("error")
    message = (
        raw_message
        if isinstance(raw_message, str) and raw_message.strip()
        else f"Request failed with status {status}"
    )
    kwargs: dict[str, Any] = {
        "status": status,
        "code": code,
        "body": body,
        "request": request,
    }

    if status == 400:
        return ValidationError(message, **kwargs)
    if status == 401:
        return AuthenticationError(message, **kwargs)
    if status == 403:
        if code == "CREDITS_EXHAUSTED":
            return CreditsExhaustedError(message, **kwargs)
        return PermissionError(message, **kwargs)
    if status == 404:
        return NotFoundError(message, **kwargs)
    if status == 429:
        limit = _numeric_header(headers, "x-ratelimit-limit")
        remaining = _numeric_header(headers, "x-ratelimit-remaining")
        return RateLimitError(
            message,
            retry_after=_numeric_header(headers, "retry-after"),
            limit=int(limit) if limit is not None else None,
            remaining=int(remaining) if remaining is not None else None,
            **kwargs,
        )
    if status >= 500:
        return ServerError(message, **kwargs)
    return ProductMapperError(message, **kwargs)
