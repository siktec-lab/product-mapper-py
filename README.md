# ProductMapper for Python

[![PyPI version](https://img.shields.io/pypi/v/productmapper.svg)](https://pypi.org/project/productmapper/)
[![Python versions](https://img.shields.io/pypi/pyversions/productmapper.svg)](https://pypi.org/project/productmapper/)
[![PyPI downloads](https://img.shields.io/pypi/dm/productmapper.svg)](https://pypi.org/project/productmapper/)
[![CI](https://github.com/siktec-lab/product-mapper-py/actions/workflows/ci.yml/badge.svg)](https://github.com/siktec-lab/product-mapper-py/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/typing-strict-blue.svg)](https://peps.python.org/pep-0561/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

Official Python client for [ProductMapper](https://product-mapper.com). Resolve a UPC, EAN, GTIN,
ASIN or free-text title into a live Amazon catalog listing: price, rating, sales rank, offers and
images, across 16 marketplace regions.

- [Website](https://product-mapper.com) | [API docs](https://product-mapper.com/docs) | [Get an API key](https://product-mapper.com/dashboard/api-keys)
- Node.js version: [@siktec-lab/productmapper on npm](https://www.npmjs.com/package/@siktec-lab/productmapper)

## Install

```bash
pip install productmapper
```

Requires Python 3.9 or newer. Fully typed, with sync and async clients.

## Quick start

```python
import os
from productmapper import ProductMapper

client = ProductMapper(api_key=os.environ["PRODUCTMAPPER_API_KEY"])

result = client.lookup(value="079361039905", type="UPC")

print(result.title)             # "Example Product"
print(result.price)             # 24.99
print(result.marketplace_id)    # "B004U9VVX6" (the matched ASIN)
```

Get your key at [product-mapper.com/dashboard/api-keys](https://product-mapper.com/dashboard/api-keys).
Keys look like `pm_live_...`, and belong in an environment variable, never in source control.

The client is also a context manager, which closes the connection pool on exit:

```python
with ProductMapper(api_key=...) as client:
    result = client.lookup(value="079361039905")
```

## Single lookup

`type` defaults to `auto`, which lets the server infer the identifier kind from the value.

```python
client.lookup(value="079361039905")                          # inferred
client.lookup(value="B004U9VVX6", type="ASIN")               # explicit
client.lookup(value="Logitech MX Master 3S", type="Title")
client.lookup(value="079361039905", region="CA")             # one region only
```

Each successful mapping costs one credit. Without a `region`, an identifier matching in several
marketplaces returns them all, and still costs a single credit. Use `.matches` to treat the one-match
and many-match cases the same way:

```python
result = client.lookup(value="079361039905")
for match in result.matches:
    print(match.amazon_marketplace_label, match.listing_details.formatted_price)
```

Full listing data lives on `result.listing_details`:

```python
listing = result.listing_details
print(listing.title, listing.brand, listing.sales_rank, listing.offer_count, listing.link)
```

Any field the API adds later is still reachable through `listing.raw["newField"]`.

### Slow lookups

When a lookup takes more than 8 seconds the API queues it and returns a job. By default the client
polls that job for you, so `lookup()` always returns a result. To take over the polling yourself,
pass `poll=False`:

```python
queued = client.lookup(value="079361039905", poll=False)

if queued.status == "processing":
    result = client.wait_for_job(queued.job_id)
    print(result.title)
```

## Batch lookups

Submit up to 500 identifiers as one background job, then wait for it:

```python
job = client.lookup_many(["079361039905", "B004U9VVX6", "Logitech MX Master 3S"])

finished = client.wait_for_batch(
    job.id,
    on_progress=lambda j: print(f"{j.processed_items}/{j.total_items}"),
)

for item in finished.items:
    print(item.identifier_value, item.title, item.price)
```

Batch rows carry a smaller field set than a single lookup. Look an identifier up individually when you
need `link`, `category`, `identifiers` or the full offer breakdown.

Export the whole batch as CSV:

```python
csv_text = client.get_batch_csv(job.id)
```

## History

Every lookup is recorded, 25 rows per page.

```python
page = client.history(page=1, search="coffee")
print(page.total, page.total_pages)

for row in page:
    print(row.identifier_value, row.title)

# Or walk every page, one row at a time.
for row in client.history_all():
    print(row.identifier_value)

client.delete_history_row(row_id)
client.clear_history()
```

## Async

`AsyncProductMapper` mirrors the sync client method for method.

```python
import asyncio
from productmapper import AsyncProductMapper

async def main():
    async with AsyncProductMapper(api_key=...) as client:
        result = await client.lookup(value="079361039905", type="UPC")
        print(result.title)

        async for row in client.history_all():
            print(row.identifier_value)

asyncio.run(main())
```

## Error handling

Every failure is a `ProductMapperError`, so one `except` can cover them all, with subclasses for the
cases worth reacting to individually.

```python
from productmapper import (
    ProductMapper,
    NotFoundError,
    RateLimitError,
    CreditsExhaustedError,
)

try:
    result = client.lookup(value="079361039905")
except NotFoundError:
    print("No match in the Amazon catalog.")
except CreditsExhaustedError:
    print("Out of credits: upgrade the plan or buy a credit pack.")
except RateLimitError as exc:
    print(f"Retry in {exc.retry_after}s, limit is {exc.limit}/min")
```

| Exception | Raised when |
| --- | --- |
| `ValidationError` | 400, or the client rejected the arguments before sending |
| `AuthenticationError` | 401, the API key is missing, malformed or revoked |
| `PermissionError` | 403, usually no active organization is selected |
| `CreditsExhaustedError` | 403 with code `CREDITS_EXHAUSTED` |
| `NotFoundError` | 404, no catalog match, or the resource is not yours |
| `RateLimitError` | 429, carries `retry_after`, `limit` and `remaining` |
| `ServerError` | 5xx |
| `TimeoutError` | a request or a polling loop ran out of time |
| `ConnectionError` | the request never reached the API |
| `JobFailedError` | a queued lookup or batch ended in a failed state |

Rate limits, server errors and network failures are retried automatically with exponential backoff,
honoring `Retry-After`. Validation and auth failures are never retried.

Note that `PermissionError`, `TimeoutError` and `ConnectionError` deliberately shadow the builtins of
the same name. Import them from `productmapper` to catch the API versions.

## Configuration

```python
client = ProductMapper(
    api_key=os.environ["PRODUCTMAPPER_API_KEY"],
    base_url="https://product-mapper.com",   # override for a self-hosted instance
    timeout=30.0,                            # per request, in seconds
    max_retries=2,                           # for 429, 5xx and network errors
    headers={"X-Team": "pricing"},           # sent with every request
)
```

## API reference

| Method | Description |
| --- | --- |
| `lookup(value, ...)` | Resolve one identifier. Polls a queued lookup unless `poll=False` |
| `lookup_many(items, ...)` | Submit up to 500 identifiers as a batch job |
| `get_job(job_id)` | Poll one queued single lookup |
| `get_jobs(job_ids)` | Poll up to 100 queued lookups in one round trip |
| `get_batch(batch_id)` | Fetch a batch job and its items |
| `get_batch_csv(batch_id)` | Export a batch job as CSV |
| `wait_for_job(job_id, ...)` | Poll a queued lookup until it resolves |
| `wait_for_batch(batch_id, ...)` | Poll a batch until every item is processed |
| `history(page=1, search=None)` | List lookup history, 25 per page |
| `history_all(search=None)` | Iterator over every history row |
| `delete_history_row(row_id)` | Delete one history row |
| `clear_history()` | Clear the entire history |

### Supported values

**Identifier types:** `auto`, `UPC`, `EAN`, `GTIN`, `ASIN`, `Title`

**Regions:** `US`, `CA`, `MX`, `BR`, `UK`, `DE`, `FR`, `IT`, `ES`, `NL`, `PL`, `SE`, `IN`, `JP`, `AU`, `SG`

Both are exported as `IDENTIFIER_TYPES` and `REGIONS`.

## Examples

Runnable scripts live in [examples/](./examples): single lookup, batch with progress and CSV export,
history paging, async usage, and full error handling.

## Links

- [ProductMapper](https://product-mapper.com)
- [API documentation](https://product-mapper.com/docs)
- [MCP server for AI agents](https://product-mapper.com/docs/api-mcp)
- [TypeScript SDK](https://github.com/siktec-lab/product-mapper-ts)
- [Report an issue](https://github.com/siktec-lab/product-mapper-py/issues)

## License

MIT, see [LICENSE](./LICENSE).
