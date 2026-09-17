"""Tests for the ProductMapper client, against a mocked HTTP layer."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from productmapper import (
    AsyncProductMapper,
    AuthenticationError,
    CreditsExhaustedError,
    JobFailedError,
    MappingResult,
    NotFoundError,
    ProductMapper,
    QueuedLookup,
    RateLimitError,
    TimeoutError,
    ValidationError,
)

API_KEY = "pm_live_test_key"

RESULT_FIXTURE: dict[str, Any] = {
    "identifierType": "UPC",
    "identifierValue": "079361039905",
    "marketplace": "amazon",
    "marketplaceId": "B004U9VVX6",
    "amazonMarketplaceLabel": "US",
    "timestamp": 1_700_000_000_000,
    "listingDetails": {
        "asin": "B004U9VVX6",
        "title": "Example Product",
        "brand": "ExampleBrand",
        "imageUrl": "https://example.com/i.jpg",
        "price": 24.99,
        "formattedPrice": "$24.99",
        "listPrice": None,
        "offerCount": 3,
        "offerCountFba": None,
        "offerCountMerchant": None,
        "isBuyBoxWinner": True,
        "salesRank": 1234,
        "link": "https://www.amazon.com/dp/B004U9VVX6",
        "isActive": True,
    },
}

BATCH_FIXTURE: dict[str, Any] = {
    "id": "batch-1",
    "userId": "user_1",
    "orgId": "org_1",
    "marketplace": "amazon",
    "totalItems": 2,
    "processedItems": 0,
    "matchedItems": 0,
    "status": "pending",
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}


class Recorder:
    """A mock transport that replays queued responses and records every request."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self._index = 0
        self.requests: list[httpx.Request] = []

    def _next(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return httpx.Response(
            status_code=response.status_code,
            content=response.content,
            headers=response.headers,
        )

    def sync(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._next)

    def asyncs(self) -> httpx.MockTransport:
        async def handler(request: httpx.Request) -> httpx.Response:
            return self._next(request)

        return httpx.MockTransport(handler)


def json_response(payload: Any, status: int = 200, headers: Any = None) -> httpx.Response:
    return httpx.Response(status_code=status, json=payload, headers=headers)


def text_response(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status, content=body.encode(), headers={"Content-Type": "text/csv"}
    )


def make_client(responses: list[httpx.Response], **kwargs: Any) -> tuple[ProductMapper, Recorder]:
    recorder = Recorder(responses)
    kwargs.setdefault("max_retries", 0)
    client = ProductMapper(API_KEY, transport=recorder.sync(), **kwargs)
    return client, recorder


class TestConstructor:
    def test_requires_an_api_key(self) -> None:
        with pytest.raises(ValidationError):
            ProductMapper("")

    def test_defaults_to_the_public_base_url(self) -> None:
        assert ProductMapper(API_KEY).base_url == "https://product-mapper.com"

    def test_strips_a_trailing_slash(self) -> None:
        assert ProductMapper(API_KEY, base_url="http://localhost:5188/").base_url == (
            "http://localhost:5188"
        )


class TestLookup:
    def test_sends_a_bearer_token_and_returns_the_result(self) -> None:
        client, rec = make_client([json_response(RESULT_FIXTURE)])
        result = client.lookup(value="079361039905", type="UPC")

        assert result.title == "Example Product"
        assert result.price == 24.99
        assert result.marketplace_id == "B004U9VVX6"
        assert result.listing_details is not None
        assert result.listing_details.sales_rank == 1234

        request = rec.requests[0]
        assert request.method == "POST"
        assert str(request.url) == "https://product-mapper.com/api/map"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"

    def test_omits_the_auto_type_and_passes_region(self) -> None:
        import json

        client, rec = make_client([json_response(RESULT_FIXTURE)])
        client.lookup(value="coffee maker", type="auto", region="CA")

        body = json.loads(rec.requests[0].content)
        assert body == {"value": "coffee maker", "region": "CA"}

    def test_rejects_an_empty_value_before_requesting(self) -> None:
        client, rec = make_client([json_response(RESULT_FIXTURE)])
        with pytest.raises(ValidationError):
            client.lookup(value="   ")
        assert rec.requests == []

    def test_polls_a_queued_lookup_until_complete(self) -> None:
        client, rec = make_client(
            [
                json_response({"status": "processing", "jobId": "job-1"}, status=202),
                json_response({"status": "processing", "message": "still going"}),
                json_response({"status": "completed", "data": RESULT_FIXTURE}),
            ]
        )
        result = client.lookup(value="079361039905", poll_interval=0.001)

        assert result.marketplace_id == "B004U9VVX6"
        assert len(rec.requests) == 3
        assert str(rec.requests[1].url) == "https://product-mapper.com/api/jobs/job-1"

    def test_returns_the_job_handle_when_polling_is_disabled(self) -> None:
        client, rec = make_client(
            [json_response({"status": "processing", "jobId": "job-2"}, status=202)]
        )
        queued = client.lookup(value="x", poll=False)

        assert isinstance(queued, QueuedLookup)
        assert queued.job_id == "job-2"
        assert len(rec.requests) == 1

    def test_raises_when_a_job_fails(self) -> None:
        client, _ = make_client(
            [
                json_response({"status": "processing", "jobId": "job-3"}, status=202),
                json_response({"status": "failed", "error": "resolution failed"}),
            ]
        )
        with pytest.raises(JobFailedError):
            client.lookup(value="x", poll_interval=0.001)

    def test_times_out_a_job_that_never_resolves(self) -> None:
        client, _ = make_client(
            [
                json_response({"status": "processing", "jobId": "job-4"}, status=202),
                json_response({"status": "processing"}),
            ]
        )
        with pytest.raises(TimeoutError):
            client.lookup(value="x", poll_interval=0.05, poll_timeout=0.001)

    def test_exposes_multi_region_matches(self) -> None:
        payload = dict(RESULT_FIXTURE)
        payload["results"] = [RESULT_FIXTURE, {**RESULT_FIXTURE, "amazonMarketplaceLabel": "CA"}]
        client, _ = make_client([json_response(payload)])

        result = client.lookup(value="079361039905")
        assert len(result.matches) == 2
        assert [m.amazon_marketplace_label for m in result.matches] == ["US", "CA"]

    def test_single_match_still_yields_one_entry(self) -> None:
        client, _ = make_client([json_response(RESULT_FIXTURE)])
        result = client.lookup(value="079361039905")
        assert len(result.matches) == 1

    def test_keeps_unknown_fields_in_raw(self) -> None:
        payload = {**RESULT_FIXTURE, "someNewField": "keep me"}
        client, _ = make_client([json_response(payload)])
        result = client.lookup(value="x")
        assert result.raw["someNewField"] == "keep me"


class TestErrors:
    def test_maps_401(self) -> None:
        client, _ = make_client([json_response({"error": "Unauthorized"}, status=401)])
        with pytest.raises(AuthenticationError):
            client.lookup(value="x")

    def test_maps_403_credits_exhausted(self) -> None:
        client, _ = make_client(
            [json_response({"error": "no credits", "code": "CREDITS_EXHAUSTED"}, status=403)]
        )
        with pytest.raises(CreditsExhaustedError) as info:
            client.lookup(value="x")
        assert info.value.code == "CREDITS_EXHAUSTED"

    def test_maps_404(self) -> None:
        client, _ = make_client([json_response({"error": "no match"}, status=404)])
        with pytest.raises(NotFoundError):
            client.lookup(value="x")

    def test_exposes_rate_limit_metadata(self) -> None:
        client, _ = make_client(
            [
                json_response(
                    {"error": "slow down", "code": "RATE_LIMITED"},
                    status=429,
                    headers={
                        "Retry-After": "7",
                        "X-RateLimit-Limit": "60",
                        "X-RateLimit-Remaining": "0",
                    },
                )
            ]
        )
        with pytest.raises(RateLimitError) as info:
            client.lookup(value="x")
        assert info.value.retry_after == 7
        assert info.value.limit == 60
        assert info.value.remaining == 0

    def test_retries_a_500_then_succeeds(self) -> None:
        client, rec = make_client(
            [json_response({"error": "boom"}, status=500), json_response(RESULT_FIXTURE)],
            max_retries=1,
        )
        result = client.lookup(value="x")
        assert result.identifier_value == "079361039905"
        assert len(rec.requests) == 2

    def test_does_not_retry_a_400(self) -> None:
        client, rec = make_client([json_response({"error": "bad"}, status=400)], max_retries=3)
        with pytest.raises(ValidationError):
            client.lookup(value="x")
        assert len(rec.requests) == 1

    def test_error_str_includes_status(self) -> None:
        client, _ = make_client([json_response({"error": "no match"}, status=404)])
        with pytest.raises(NotFoundError) as info:
            client.lookup(value="x")
        assert str(info.value) == "[404] no match"


class TestBatch:
    def test_submits_items(self) -> None:
        import json

        client, rec = make_client([json_response(BATCH_FIXTURE, status=202)])
        job = client.lookup_many(["079361039905", "B004U9VVX6"])

        assert job.id == "batch-1"
        assert job.total_items == 2
        body = json.loads(rec.requests[0].content)
        assert body == {"items": ["079361039905", "B004U9VVX6"]}

    def test_rejects_empty_and_oversized_lists(self) -> None:
        client, _ = make_client([json_response(BATCH_FIXTURE)])
        with pytest.raises(ValidationError):
            client.lookup_many([])
        with pytest.raises(ValidationError):
            client.lookup_many(["x"] * 501)

    def test_waits_and_reports_progress(self) -> None:
        client, _ = make_client(
            [
                json_response({**BATCH_FIXTURE, "status": "processing", "processedItems": 1}),
                json_response(
                    {
                        **BATCH_FIXTURE,
                        "status": "completed",
                        "processedItems": 2,
                        "matchedItems": 2,
                    }
                ),
            ]
        )
        seen: list[int] = []
        job = client.wait_for_batch(
            "batch-1", interval=0.001, on_progress=lambda j: seen.append(j.processed_items)
        )

        assert job.status == "completed"
        assert job.is_done
        assert job.progress == 1.0
        assert seen == [1, 2]

    def test_raises_on_a_failed_batch(self) -> None:
        client, _ = make_client([json_response({**BATCH_FIXTURE, "status": "failed"})])
        with pytest.raises(JobFailedError):
            client.wait_for_batch("batch-1", interval=0.001)

    def test_parses_items(self) -> None:
        payload = {
            **BATCH_FIXTURE,
            "status": "completed",
            "items": [
                {
                    "id": "i1",
                    "identifierType": "UPC",
                    "identifierValue": "079361039905",
                    "title": "Example Product",
                    "price": 24.99,
                    "status": "completed",
                },
                {
                    "id": "i2",
                    "identifierType": "UPC",
                    "identifierValue": "000000000000",
                    "status": "not_found",
                },
            ],
        }
        client, _ = make_client([json_response(payload)])
        job = client.get_batch("batch-1")

        assert len(job.items) == 2
        assert job.items[0].title == "Example Product"
        assert job.items[0].price == 24.99
        assert job.items[1].status == "not_found"
        assert job.items[1].title is None

    def test_fetches_a_csv_export(self) -> None:
        client, rec = make_client([text_response("id,title\n1,Example")])
        csv_text = client.get_batch_csv("batch-1")

        assert csv_text == "id,title\n1,Example"
        assert "format=csv" in str(rec.requests[0].url)


class TestJobs:
    def test_joins_ids_for_a_multi_job_poll(self) -> None:
        client, rec = make_client(
            [
                json_response(
                    {
                        "jobs": {
                            "a": {"status": "processing"},
                            "b": {"status": "failed", "error": "x"},
                        }
                    }
                )
            ]
        )
        jobs = client.get_jobs(["a", "b"])

        assert set(jobs) == {"a", "b"}
        assert jobs["b"].error == "x"
        assert jobs["b"].is_done
        assert "ids=a%2Cb" in str(rec.requests[0].url)

    def test_rejects_more_than_100_ids(self) -> None:
        client, _ = make_client([json_response({"jobs": {}})])
        with pytest.raises(ValidationError):
            client.get_jobs(["a"] * 101)


def history_payload(page: int, total_pages: int) -> dict[str, Any]:
    return {
        "history": [
            {
                "id": f"row-{page}",
                "identifierType": "UPC",
                "identifierValue": f"0000{page}",
                "marketplace": "amazon",
                "status": "completed",
                "createdAt": "2026-01-01T00:00:00Z",
            }
        ],
        "page": page,
        "pageSize": 25,
        "total": total_pages,
        "totalPages": total_pages,
    }


class TestHistory:
    def test_passes_page_and_search(self) -> None:
        client, rec = make_client([json_response(history_payload(2, 2))])
        page = client.history(page=2, search="coffee")

        url = str(rec.requests[0].url)
        assert "page=2" in url
        assert "search=coffee" in url
        assert page.page == 2
        assert len(page) == 1

    def test_iterates_a_page(self) -> None:
        client, _ = make_client([json_response(history_payload(1, 1))])
        rows = list(client.history(page=1))
        assert rows[0].identifier_value == "00001"

    def test_walks_every_page(self) -> None:
        client, _ = make_client(
            [
                json_response(history_payload(1, 3)),
                json_response(history_payload(2, 3)),
                json_response(history_payload(3, 3)),
            ]
        )
        ids = [row.id for row in client.history_all()]
        assert ids == ["row-1", "row-2", "row-3"]

    def test_deletes_a_row_and_clears(self) -> None:
        client, rec = make_client(
            [json_response({"success": True}), json_response({"success": True})]
        )
        client.delete_history_row("row-1")
        client.clear_history()

        assert rec.requests[0].method == "DELETE"
        assert str(rec.requests[0].url) == "https://product-mapper.com/api/history/row-1"
        assert str(rec.requests[1].url) == "https://product-mapper.com/api/history"


class TestAsyncClient:
    async def test_lookup(self) -> None:
        recorder = Recorder([json_response(RESULT_FIXTURE)])
        async with AsyncProductMapper(
            API_KEY, transport=recorder.asyncs(), max_retries=0
        ) as client:
            result = await client.lookup(value="079361039905", type="UPC")

        assert result.title == "Example Product"
        assert recorder.requests[0].headers["authorization"] == f"Bearer {API_KEY}"

    async def test_polls_a_queued_lookup(self) -> None:
        recorder = Recorder(
            [
                json_response({"status": "processing", "jobId": "job-9"}, status=202),
                json_response({"status": "completed", "data": RESULT_FIXTURE}),
            ]
        )
        async with AsyncProductMapper(
            API_KEY, transport=recorder.asyncs(), max_retries=0
        ) as client:
            result = await client.lookup(value="x", poll_interval=0.001)

        assert result.marketplace_id == "B004U9VVX6"
        assert len(recorder.requests) == 2

    async def test_raises_typed_errors(self) -> None:
        recorder = Recorder([json_response({"error": "no match"}, status=404)])
        async with AsyncProductMapper(
            API_KEY, transport=recorder.asyncs(), max_retries=0
        ) as client:
            with pytest.raises(NotFoundError):
                await client.lookup(value="x")

    async def test_history_all(self) -> None:
        recorder = Recorder(
            [json_response(history_payload(1, 2)), json_response(history_payload(2, 2))]
        )
        async with AsyncProductMapper(
            API_KEY, transport=recorder.asyncs(), max_retries=0
        ) as client:
            ids = [row.id async for row in client.history_all()]

        assert ids == ["row-1", "row-2"]


class TestTypedLookupReturn:
    """The overloads on lookup() mean a default call needs no narrowing."""

    def test_default_call_returns_a_mapping_result(self) -> None:
        client, _ = make_client([json_response(RESULT_FIXTURE)])
        result = client.lookup(value="079361039905")
        # Reached without an isinstance check, which is the point of the overload.
        assert result.title == "Example Product"

    def test_poll_false_can_return_either(self) -> None:
        client, _ = make_client([json_response(RESULT_FIXTURE)])
        result = client.lookup(value="079361039905", poll=False)
        assert isinstance(result, MappingResult)
