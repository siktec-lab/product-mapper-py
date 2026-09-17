"""The ProductMapper client: one method per public API operation, plus polling helpers
that turn the queue-based endpoints into a single call.

Both a synchronous :class:`ProductMapper` and an asynchronous :class:`AsyncProductMapper`
are provided. They expose the same method names and arguments, so moving between them is
a matter of adding ``await``.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from types import TracebackType
from typing import (
    Any,
    Callable,
    Literal,
    Union,
    overload,
)

import httpx

from ._version import __version__
from .exceptions import (
    ConnectionError,
    JobFailedError,
    ProductMapperError,
    RateLimitError,
    ServerError,
    TimeoutError,
    ValidationError,
    error_from_response,
)
from .models import BatchJob, HistoryPage, HistoryRow, JobStatus, MappingResult, QueuedLookup

__all__ = ["DEFAULT_BASE_URL", "AsyncProductMapper", "ProductMapper"]

DEFAULT_BASE_URL = "https://product-mapper.com"

MAX_BATCH_ITEMS = 500
MAX_JOB_IDS = 100
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_JOB_TIMEOUT = 120.0
DEFAULT_JOB_INTERVAL = 1.5
DEFAULT_BATCH_TIMEOUT = 600.0
DEFAULT_BATCH_INTERVAL = 3.0
#: Never sleep longer than this between retries, even if Retry-After asks for more.
MAX_RETRY_DELAY = 30.0

LookupReturn = Union[MappingResult, QueuedLookup]


class _RequestSpec:
    """One prepared request, shared by the sync and async paths."""

    __slots__ = ("json", "label", "method", "params", "path")

    def __init__(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        self.json = json
        self.label = f"{method} {path}"


def _backoff_delay(attempt: int) -> float:
    """Full jitter backoff, so a fleet of clients does not retry in lockstep."""
    base: float = min(float(2**attempt), MAX_RETRY_DELAY)
    return base * (0.5 + random.random() * 0.5)


def _retry_delay(error: ProductMapperError, attempt: int) -> float:
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        return min(error.retry_after, MAX_RETRY_DELAY)
    return _backoff_delay(attempt)


def _is_retryable(error: ProductMapperError) -> bool:
    return isinstance(error, (RateLimitError, ServerError, ConnectionError, TimeoutError))


def _parse_body(response: httpx.Response, label: str) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise ProductMapperError(
            f"{label} returned a non-JSON response",
            status=response.status_code,
            body=response.text,
            request=label,
        ) from exc


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or None


def _wrap_transport_error(exc: Exception, label: str) -> ProductMapperError:
    if isinstance(exc, httpx.TimeoutException):
        return TimeoutError(f"{label} timed out", request=label)
    return ConnectionError(f"{label} failed: {exc}", request=label)


class _BaseClient:
    """Configuration and request-building shared by both clients."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not api_key or not isinstance(api_key, str):
            raise ValidationError(
                "An api_key is required. Generate one at "
                "https://product-mapper.com/dashboard/api-keys"
            )
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": f"productmapper-python/{__version__}",
            **dict(headers or {}),
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _lookup_payload(
        value: str,
        type: str | None,
        marketplace: str | None,
        region: str | None,
    ) -> dict[str, Any]:
        if not value or not isinstance(value, str) or not value.strip():
            raise ValidationError('lookup() requires a non-empty "value"')
        payload: dict[str, Any] = {"value": value}
        if type and type != "auto":
            payload["type"] = type
        if marketplace:
            payload["marketplace"] = marketplace
        if region:
            payload["region"] = region
        return payload

    @staticmethod
    def _batch_payload(items: Sequence[str], marketplace: str | None) -> dict[str, Any]:
        if not items:
            raise ValidationError("lookup_many() requires a non-empty sequence of identifiers")
        if len(items) > MAX_BATCH_ITEMS:
            raise ValidationError(
                f"lookup_many() accepts at most {MAX_BATCH_ITEMS} items per request, "
                f"got {len(items)}"
            )
        payload: dict[str, Any] = {"items": list(items)}
        if marketplace:
            payload["marketplace"] = marketplace
        return payload

    @staticmethod
    def _job_ids_param(job_ids: Sequence[str]) -> str:
        if not job_ids:
            raise ValidationError("get_jobs() requires a non-empty sequence of job ids")
        if len(job_ids) > MAX_JOB_IDS:
            raise ValidationError(
                f"get_jobs() accepts at most {MAX_JOB_IDS} ids per request, got {len(job_ids)}"
            )
        return ",".join(job_ids)

    @staticmethod
    def _require(value: str, method: str, what: str) -> str:
        if not value:
            raise ValidationError(f"{method} requires {what}")
        return value


class ProductMapper(_BaseClient):
    """Synchronous client for the ProductMapper API.

    ::

        from productmapper import ProductMapper

        client = ProductMapper(api_key="pm_live_...")
        result = client.lookup(value="079361039905", type="UPC")
        print(result.title, result.price)

    The client can be used as a context manager, which closes the underlying connection
    pool on exit.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            headers=headers,
        )
        self._client = httpx.Client(
            timeout=timeout,
            headers=self._headers,
            transport=transport,
            follow_redirects=True,
        )

    def __enter__(self) -> ProductMapper:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._client.close()

    def _request(self, spec: _RequestSpec, *, as_text: bool = False) -> Any:
        last_error: ProductMapperError | None = None

        for attempt in range(self._max_retries + 1):
            if attempt > 0 and last_error is not None:
                time.sleep(_retry_delay(last_error, attempt - 1))

            try:
                response = self._client.request(
                    spec.method,
                    self._url(spec.path),
                    params=spec.params or None,
                    json=spec.json,
                )
            except httpx.HTTPError as exc:
                wrapped = _wrap_transport_error(exc, spec.label)
                if attempt == self._max_retries:
                    raise wrapped from exc
                last_error = wrapped
                continue

            if response.is_success:
                return response.text if as_text else _parse_body(response, spec.label)

            error = error_from_response(
                response.status_code, _safe_body(response), spec.label, response.headers
            )
            if not _is_retryable(error) or attempt == self._max_retries:
                raise error
            last_error = error

        raise last_error or ProductMapperError(f"{spec.label} failed", request=spec.label)

    @overload
    def lookup(
        self,
        value: str,
        *,
        type: str | None = ...,
        marketplace: str | None = ...,
        region: str | None = ...,
        poll: Literal[True] = ...,
        poll_timeout: float = ...,
        poll_interval: float = ...,
    ) -> MappingResult: ...

    @overload
    def lookup(
        self,
        value: str,
        *,
        type: str | None = ...,
        marketplace: str | None = ...,
        region: str | None = ...,
        poll: Literal[False],
        poll_timeout: float = ...,
        poll_interval: float = ...,
    ) -> LookupReturn: ...

    def lookup(
        self,
        value: str,
        *,
        type: str | None = None,
        marketplace: str | None = None,
        region: str | None = None,
        poll: bool = True,
        poll_timeout: float = DEFAULT_JOB_TIMEOUT,
        poll_interval: float = DEFAULT_JOB_INTERVAL,
    ) -> LookupReturn:
        """Resolve a single UPC, EAN, GTIN, ASIN or free-text title.

        Charges one credit per successful mapping.

        If the server needs more than 8 seconds it queues the work and returns a job.
        By default this polls that job until it resolves, so you always get a
        :class:`MappingResult`. Pass ``poll=False`` to receive a :class:`QueuedLookup`
        instead and drive the polling yourself.

        :raises NotFoundError: the identifier has no match in the Amazon catalog.
        :raises CreditsExhaustedError: the organization is out of credits.
        :raises RateLimitError: the plan requests-per-minute ceiling was exceeded.
        """
        payload = self._lookup_payload(value, type, marketplace, region)
        data = self._request(_RequestSpec("POST", "api/map", json=payload))

        if _is_queued(data):
            queued = QueuedLookup.from_dict(data)
            if not poll:
                return queued
            return self.wait_for_job(queued.job_id, timeout=poll_timeout, interval=poll_interval)

        return MappingResult.from_dict(data or {})

    def lookup_many(self, items: Sequence[str], *, marketplace: str | None = None) -> BatchJob:
        """Submit up to 500 identifiers as one background batch job.

        Returns as soon as the job is created. Poll it with :meth:`get_batch`, or use
        :meth:`wait_for_batch` to block until every item is processed.
        """
        payload = self._batch_payload(items, marketplace)
        data = self._request(_RequestSpec("POST", "api/map/batch", json=payload))
        return BatchJob.from_dict(data or {})

    def get_job(self, job_id: str) -> JobStatus:
        """Poll one queued single lookup by its job id."""
        self._require(job_id, "get_job()", "a job id")
        data = self._request(_RequestSpec("GET", f"api/jobs/{job_id}"))
        return JobStatus.from_dict(data or {})

    def get_jobs(self, job_ids: Sequence[str]) -> dict[str, JobStatus]:
        """Poll up to 100 queued single lookups in one round trip."""
        ids = self._job_ids_param(job_ids)
        data = self._request(_RequestSpec("GET", "api/jobs", params={"ids": ids}))
        jobs = (data or {}).get("jobs") or {}
        return {k: JobStatus.from_dict(v) for k, v in jobs.items() if isinstance(v, dict)}

    def get_batch(self, batch_id: str) -> BatchJob:
        """Fetch a batch job, including its items once processing has started."""
        self._require(batch_id, "get_batch()", "a batch id")
        data = self._request(_RequestSpec("GET", f"api/jobs/batch/{batch_id}"))
        return BatchJob.from_dict(data or {})

    def get_batch_csv(self, batch_id: str) -> str:
        """Export a batch job as an RFC 4180 CSV string."""
        self._require(batch_id, "get_batch_csv()", "a batch id")
        result = self._request(
            _RequestSpec("GET", f"api/jobs/batch/{batch_id}", params={"format": "csv"}),
            as_text=True,
        )
        return str(result)

    def history(self, *, page: int = 1, search: str | None = None) -> HistoryPage:
        """List your lookup history, 25 rows per page.

        ``search`` matches identifier value or product title, case-insensitive and partial.
        """
        data = self._request(
            _RequestSpec("GET", "api/history", params={"page": page, "search": search})
        )
        return HistoryPage.from_dict(data or {})

    def history_all(self, *, search: str | None = None) -> Iterator[HistoryRow]:
        """Iterate every history row across all pages, fetching each page as you go."""
        page = 1
        total_pages = 1
        while page <= total_pages:
            result = self.history(page=page, search=search)
            total_pages = max(result.total_pages, 1)
            yield from result.history
            page += 1

    def clear_history(self) -> None:
        """Clear your entire lookup history.

        Rows are hidden at once and hard-deleted after 24 hours.
        """
        self._request(_RequestSpec("DELETE", "api/history"))

    def delete_history_row(self, row_id: str) -> None:
        """Delete one history row by id."""
        self._require(row_id, "delete_history_row()", "a row id")
        self._request(_RequestSpec("DELETE", f"api/history/{row_id}"))

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float = DEFAULT_JOB_TIMEOUT,
        interval: float = DEFAULT_JOB_INTERVAL,
    ) -> MappingResult:
        """Poll a queued single lookup until it completes, fails or times out.

        :raises JobFailedError: the job ended in a failed state.
        :raises TimeoutError: the job was still processing at the deadline.
        """
        deadline = time.monotonic() + timeout
        while True:
            status = self.get_job(job_id)
            if status.status == "completed":
                return status.data or MappingResult.from_dict(status.raw.get("data") or {})
            if status.status == "failed":
                raise JobFailedError(
                    status.error or f"Job {job_id} failed", job_id=job_id, body=status.raw
                )
            if time.monotonic() + interval > deadline:
                raise TimeoutError(
                    f"Job {job_id} was still processing after {timeout}s. "
                    f'Poll get_job("{job_id}") to keep waiting.'
                )
            time.sleep(interval)

    def wait_for_batch(
        self,
        batch_id: str,
        *,
        timeout: float = DEFAULT_BATCH_TIMEOUT,
        interval: float = DEFAULT_BATCH_INTERVAL,
        on_progress: Callable[[BatchJob], None] | None = None,
    ) -> BatchJob:
        """Poll a batch job until every item is processed, or it fails or times out.

        ``on_progress`` is called after each poll, which is where a progress bar belongs.

        :raises JobFailedError: the batch ended in a failed state.
        :raises TimeoutError: the batch was still running at the deadline.
        """
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_batch(batch_id)
            if on_progress is not None:
                on_progress(job)
            if job.status == "completed":
                return job
            if job.status == "failed":
                raise JobFailedError(f"Batch job {batch_id} failed", job_id=batch_id, body=job.raw)
            if time.monotonic() + interval > deadline:
                raise TimeoutError(
                    f"Batch job {batch_id} was still running after {timeout}s "
                    f"({job.processed_items}/{job.total_items} processed). "
                    f'Poll get_batch("{batch_id}") to keep waiting.'
                )
            time.sleep(interval)


class AsyncProductMapper(_BaseClient):
    """Asynchronous client for the ProductMapper API.

    Mirrors :class:`ProductMapper` method for method::

        async with AsyncProductMapper(api_key="pm_live_...") as client:
            result = await client.lookup(value="079361039905", type="UPC")
            print(result.title, result.price)
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        headers: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            headers=headers,
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=self._headers,
            transport=transport,
            follow_redirects=True,
        )

    async def __aenter__(self) -> AsyncProductMapper:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying connection pool."""
        await self._client.aclose()

    async def _request(self, spec: _RequestSpec, *, as_text: bool = False) -> Any:
        last_error: ProductMapperError | None = None

        for attempt in range(self._max_retries + 1):
            if attempt > 0 and last_error is not None:
                await asyncio.sleep(_retry_delay(last_error, attempt - 1))

            try:
                response = await self._client.request(
                    spec.method,
                    self._url(spec.path),
                    params=spec.params or None,
                    json=spec.json,
                )
            except httpx.HTTPError as exc:
                wrapped = _wrap_transport_error(exc, spec.label)
                if attempt == self._max_retries:
                    raise wrapped from exc
                last_error = wrapped
                continue

            if response.is_success:
                return response.text if as_text else _parse_body(response, spec.label)

            error = error_from_response(
                response.status_code, _safe_body(response), spec.label, response.headers
            )
            if not _is_retryable(error) or attempt == self._max_retries:
                raise error
            last_error = error

        raise last_error or ProductMapperError(f"{spec.label} failed", request=spec.label)

    @overload
    async def lookup(
        self,
        value: str,
        *,
        type: str | None = ...,
        marketplace: str | None = ...,
        region: str | None = ...,
        poll: Literal[True] = ...,
        poll_timeout: float = ...,
        poll_interval: float = ...,
    ) -> MappingResult: ...

    @overload
    async def lookup(
        self,
        value: str,
        *,
        type: str | None = ...,
        marketplace: str | None = ...,
        region: str | None = ...,
        poll: Literal[False],
        poll_timeout: float = ...,
        poll_interval: float = ...,
    ) -> LookupReturn: ...

    async def lookup(
        self,
        value: str,
        *,
        type: str | None = None,
        marketplace: str | None = None,
        region: str | None = None,
        poll: bool = True,
        poll_timeout: float = DEFAULT_JOB_TIMEOUT,
        poll_interval: float = DEFAULT_JOB_INTERVAL,
    ) -> LookupReturn:
        """Resolve a single identifier. See :meth:`ProductMapper.lookup`."""
        payload = self._lookup_payload(value, type, marketplace, region)
        data = await self._request(_RequestSpec("POST", "api/map", json=payload))

        if _is_queued(data):
            queued = QueuedLookup.from_dict(data)
            if not poll:
                return queued
            return await self.wait_for_job(
                queued.job_id, timeout=poll_timeout, interval=poll_interval
            )

        return MappingResult.from_dict(data or {})

    async def lookup_many(
        self, items: Sequence[str], *, marketplace: str | None = None
    ) -> BatchJob:
        """Submit up to 500 identifiers as one background batch job."""
        payload = self._batch_payload(items, marketplace)
        data = await self._request(_RequestSpec("POST", "api/map/batch", json=payload))
        return BatchJob.from_dict(data or {})

    async def get_job(self, job_id: str) -> JobStatus:
        """Poll one queued single lookup by its job id."""
        self._require(job_id, "get_job()", "a job id")
        data = await self._request(_RequestSpec("GET", f"api/jobs/{job_id}"))
        return JobStatus.from_dict(data or {})

    async def get_jobs(self, job_ids: Sequence[str]) -> dict[str, JobStatus]:
        """Poll up to 100 queued single lookups in one round trip."""
        ids = self._job_ids_param(job_ids)
        data = await self._request(_RequestSpec("GET", "api/jobs", params={"ids": ids}))
        jobs = (data or {}).get("jobs") or {}
        return {k: JobStatus.from_dict(v) for k, v in jobs.items() if isinstance(v, dict)}

    async def get_batch(self, batch_id: str) -> BatchJob:
        """Fetch a batch job, including its items once processing has started."""
        self._require(batch_id, "get_batch()", "a batch id")
        data = await self._request(_RequestSpec("GET", f"api/jobs/batch/{batch_id}"))
        return BatchJob.from_dict(data or {})

    async def get_batch_csv(self, batch_id: str) -> str:
        """Export a batch job as an RFC 4180 CSV string."""
        self._require(batch_id, "get_batch_csv()", "a batch id")
        result = await self._request(
            _RequestSpec("GET", f"api/jobs/batch/{batch_id}", params={"format": "csv"}),
            as_text=True,
        )
        return str(result)

    async def history(self, *, page: int = 1, search: str | None = None) -> HistoryPage:
        """List your lookup history, 25 rows per page."""
        data = await self._request(
            _RequestSpec("GET", "api/history", params={"page": page, "search": search})
        )
        return HistoryPage.from_dict(data or {})

    async def history_all(self, *, search: str | None = None) -> AsyncIterator[HistoryRow]:
        """Iterate every history row across all pages, fetching each page as you go."""
        page = 1
        total_pages = 1
        while page <= total_pages:
            result = await self.history(page=page, search=search)
            total_pages = max(result.total_pages, 1)
            for row in result.history:
                yield row
            page += 1

    async def clear_history(self) -> None:
        """Clear your entire lookup history."""
        await self._request(_RequestSpec("DELETE", "api/history"))

    async def delete_history_row(self, row_id: str) -> None:
        """Delete one history row by id."""
        self._require(row_id, "delete_history_row()", "a row id")
        await self._request(_RequestSpec("DELETE", f"api/history/{row_id}"))

    async def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float = DEFAULT_JOB_TIMEOUT,
        interval: float = DEFAULT_JOB_INTERVAL,
    ) -> MappingResult:
        """Poll a queued single lookup until it completes, fails or times out."""
        deadline = time.monotonic() + timeout
        while True:
            status = await self.get_job(job_id)
            if status.status == "completed":
                return status.data or MappingResult.from_dict(status.raw.get("data") or {})
            if status.status == "failed":
                raise JobFailedError(
                    status.error or f"Job {job_id} failed", job_id=job_id, body=status.raw
                )
            if time.monotonic() + interval > deadline:
                raise TimeoutError(
                    f"Job {job_id} was still processing after {timeout}s. "
                    f'Poll get_job("{job_id}") to keep waiting.'
                )
            await asyncio.sleep(interval)

    async def wait_for_batch(
        self,
        batch_id: str,
        *,
        timeout: float = DEFAULT_BATCH_TIMEOUT,
        interval: float = DEFAULT_BATCH_INTERVAL,
        on_progress: Callable[[BatchJob], None] | None = None,
    ) -> BatchJob:
        """Poll a batch job until every item is processed, or it fails or times out."""
        deadline = time.monotonic() + timeout
        while True:
            job = await self.get_batch(batch_id)
            if on_progress is not None:
                on_progress(job)
            if job.status == "completed":
                return job
            if job.status == "failed":
                raise JobFailedError(f"Batch job {batch_id} failed", job_id=batch_id, body=job.raw)
            if time.monotonic() + interval > deadline:
                raise TimeoutError(
                    f"Batch job {batch_id} was still running after {timeout}s "
                    f"({job.processed_items}/{job.total_items} processed). "
                    f'Poll get_batch("{batch_id}") to keep waiting.'
                )
            await asyncio.sleep(interval)


def _is_queued(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and data.get("status") == "processing"
        and isinstance(data.get("jobId"), str)
    )
