# ProductMapper Python SDK: UPC to ASIN Lookup API Client

[![PyPI version](https://img.shields.io/pypi/v/productmapper.svg?logo=pypi&logoColor=white)](https://pypi.org/project/productmapper/)
[![Python versions](https://img.shields.io/pypi/pyversions/productmapper.svg?logo=python&logoColor=white)](https://pypi.org/project/productmapper/)
[![PyPI downloads](https://img.shields.io/pypi/dm/productmapper.svg)](https://pypi.org/project/productmapper/)
[![CI](https://github.com/siktec-lab/product-mapper-py/actions/workflows/ci.yml/badge.svg)](https://github.com/siktec-lab/product-mapper-py/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/typing-strict-blue.svg)](https://peps.python.org/pep-0561/)
[![Ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

Official **Python client** for the [ProductMapper API](https://product-mapper.com). Convert a
**UPC, EAN, GTIN, ASIN or product title into live Amazon listing data**: price, sales rank (BSR),
offer counts, Buy Box status, brand, category and images, across 16 Amazon marketplaces.

Use it to build **barcode to ASIN lookup**, retail arbitrage tooling, competitor price monitoring,
catalog enrichment, and product data pipelines, with sync and async clients and full type hints.

**[Website](https://product-mapper.com)** -
**[API Documentation](https://product-mapper.com/docs)** -
**[Get a Free API Key](https://product-mapper.com/dashboard/api-keys)** -
**[Node.js SDK](https://github.com/siktec-lab/product-mapper-ts)**

## Contents

- [Why ProductMapper](#why-productmapper)
- [Install](#install)
- [Quick start](#quick-start)
- [Convert UPC to ASIN](#convert-upc-to-asin)
- [Bulk UPC to ASIN conversion](#bulk-upc-to-asin-conversion)
- [Lookup history](#lookup-history)
- [Async client](#async-client)
- [Error handling](#error-handling)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [FAQ](#faq)

## Why ProductMapper

| Feature | Detail |
| --- | --- |
| Identifier types | UPC, EAN, GTIN, ASIN, free-text title, or `auto` detection |
| Amazon marketplaces | 16 regions including US, CA, UK, DE, FR, IT, ES, JP, AU, IN |
| Batch size | Up to 500 identifiers per background job, with CSV export |
| Data returned | Price, list price, sales rank, offer counts, FBA/merchant split, Buy Box, brand, category, images |
| Clients | Synchronous and asyncio, both fully type hinted |
| Python | 3.9 through 3.13 |

## Install

```bash
pip install productmapper
```

```bash
uv add productmapper
# or
poetry add productmapper
```

Requires Python 3.9 or newer. Ships `py.typed` for full editor and mypy support.

## Quick start

```python
import os
from productmapper import ProductMapper

client = ProductMapper(api_key=os.environ["PRODUCTMAPPER_API_KEY"])

result = client.lookup(value="753933140816", type="UPC")

print(result.marketplace_id)                  # "B09Z2J1MP2" (the matched ASIN)
print(result.title)                           # "Husky Liners Weatherbeater Floor Mats"
print(result.price)                           # 80.99
print(result.listing_details.sales_rank)      # 67364
```

Get a free API key at
[product-mapper.com/dashboard/api-keys](https://product-mapper.com/dashboard/api-keys). Keys look like
`pm_live_...` and belong in an environment variable, never in source control.

The client is also a context manager, which closes the connection pool on exit:

```python
with ProductMapper(api_key=...) as client:
    result = client.lookup(value="753933140816")
```

## Convert UPC to ASIN

`type` defaults to `auto`, so the server detects whether you passed a UPC, EAN, GTIN or ASIN.

```python
client.lookup(value="753933140816")                            # auto-detected
client.lookup(value="753933140816", type="UPC")                # UPC to ASIN
client.lookup(value="0885909950805", type="EAN")               # EAN to ASIN
client.lookup(value="B09Z2J1MP2", type="ASIN")                 # ASIN lookup
client.lookup(value="Logitech MX Master 3S", type="Title")     # title search
client.lookup(value="753933140816", region="DE")               # scope to one marketplace
```

Each successful mapping costs one credit. Without a `region`, an identifier that matches in several
Amazon marketplaces returns them all, and still costs a single credit. Use `.matches` to handle the
one-match and many-match cases the same way:

```python
result = client.lookup(value="753933140816")

for match in result.matches:
    print(match.amazon_marketplace_label, match.listing_details.formatted_price)
```

### Full listing fields

```python
listing = result.listing_details

listing.asin                   # "B09Z2J1MP2"
listing.title                  # product title
listing.brand                  # "Husky Liners"
listing.price                  # 80.99
listing.list_price             # 89.99
listing.formatted_price        # "$80.99"
listing.sales_rank             # 67364  (Best Sellers Rank)
listing.offer_count            # 5
listing.offer_count_fba        # 1
listing.offer_count_merchant   # 4
listing.is_buy_box_winner      # True
listing.category               # "Floor Mats"
listing.category_group         # "Automotive Parts and Accessories"
listing.image_url              # product image
listing.link                   # Amazon product URL
```

Any field the API adds later is still reachable through `listing.raw["newField"]`.

### Slow lookups

If a lookup takes more than 8 seconds the API returns a job instead of a result. The client polls that
job automatically, so `lookup()` always returns a result. To manage polling yourself:

```python
queued = client.lookup(value="753933140816", poll=False)

if queued.status == "processing":
    result = client.wait_for_job(queued.job_id)
```

## Bulk UPC to ASIN conversion

Submit up to 500 identifiers as one background job:

```python
job = client.lookup_many(["753933140816", "B09Z2J1MP2", "Logitech MX Master 3S"])

finished = client.wait_for_batch(
    job.id,
    on_progress=lambda j: print(f"{j.processed_items}/{j.total_items}"),
)

for item in finished.items:
    print(item.identifier_value, item.title, item.price, item.status)
```

Export results as CSV, ready for Excel or Google Sheets:

```python
from pathlib import Path

csv_text = client.get_batch_csv(job.id)
Path("asin-results.csv").write_text(csv_text, encoding="utf-8")
```

Batch rows carry fewer fields than a single lookup. Look an identifier up individually when you need
`link`, `category`, `identifiers` or the full offer breakdown.

## Lookup history

Every lookup is recorded, 25 rows per page.

```python
page = client.history(page=1, search="husky")
print(page.total, page.total_pages)

for row in page:
    print(row.identifier_value, row.title, row.status)

# Or walk every page, one row at a time.
for row in client.history_all():
    print(row.identifier_value)

client.delete_history_row(row_id)
client.clear_history()
```

History rows report `status` as `success` or `not_found`, while batch items report `completed`.

## Async client

`AsyncProductMapper` mirrors the sync client method for method.

```python
import asyncio
from productmapper import AsyncProductMapper

async def main():
    async with AsyncProductMapper(api_key=...) as client:
        result = await client.lookup(value="753933140816", type="UPC")
        print(result.title)

        # Resolve many identifiers concurrently.
        results = await asyncio.gather(
            *(client.lookup(value=v) for v in ["753933140816", "B09Z2J1MP2"]),
            return_exceptions=True,
        )

        async for row in client.history_all():
            print(row.identifier_value)

asyncio.run(main())
```

## Error handling

Every failure is a `ProductMapperError`, so one `except` can cover them all, with subclasses for the
cases worth handling individually.

```python
from productmapper import (
    NotFoundError,
    RateLimitError,
    CreditsExhaustedError,
)

try:
    result = client.lookup(value="753933140816")
except NotFoundError:
    print("No match in the Amazon catalog.")
except CreditsExhaustedError:
    print("Out of credits: upgrade the plan or buy a credit pack.")
except RateLimitError as exc:
    print(f"Retry in {exc.retry_after}s, limit is {exc.limit}/min")
```

| Exception | HTTP | Raised when |
| --- | --- | --- |
| `ValidationError` | 400 | Bad arguments, rejected before or by the API |
| `AuthenticationError` | 401 | API key missing, malformed or revoked |
| `PermissionError` | 403 | No active organization selected |
| `CreditsExhaustedError` | 403 | Credit balance is empty |
| `NotFoundError` | 404 | No catalog match, or the resource is not yours |
| `RateLimitError` | 429 | Plan requests-per-minute exceeded |
| `ServerError` | 5xx | The API failed to handle the request |
| `TimeoutError` | - | A request or polling loop ran out of time |
| `ConnectionError` | - | The request never reached the API |
| `JobFailedError` | - | A queued lookup or batch ended in a failed state |

Rate limits, server errors and network failures are retried automatically with exponential backoff,
honoring `Retry-After`. Validation and auth failures are never retried.

`PermissionError`, `TimeoutError` and `ConnectionError` deliberately shadow the builtins of the same
name. Import them from `productmapper` to catch the API versions.

## Configuration

```python
client = ProductMapper(
    api_key=os.environ["PRODUCTMAPPER_API_KEY"],
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

**Identifier types:** `auto`, `UPC`, `EAN`, `GTIN`, `ASIN`, `Title`

**Amazon marketplaces:** `US`, `CA`, `MX`, `BR`, `UK`, `DE`, `FR`, `IT`, `ES`, `NL`, `PL`, `SE`, `IN`,
`JP`, `AU`, `SG`

Both are exported as `IDENTIFIER_TYPES` and `REGIONS`.

## Examples

Runnable scripts live in [examples/](./examples): single lookup, batch with progress and CSV export,
history paging, async usage, and full error handling.

## FAQ

**How do I convert a UPC to an ASIN in Python?**
Install the package, create a client with your API key, and call
`client.lookup(value="<upc>", type="UPC")`. The matched ASIN is `result.marketplace_id`.

**Can I look up many barcodes at once?**
Yes. `lookup_many()` accepts up to 500 identifiers per batch job, and `get_batch_csv()` exports
results as CSV.

**Does it support asyncio?**
Yes. `AsyncProductMapper` mirrors the sync client method for method.

**Which Amazon marketplaces are supported?**
16 regions, listed above. Pass `region` to scope a lookup, or omit it to search across regions.

**Does it work with pandas?**
Yes. Batch items and history rows expose plain attributes and a `raw` dict, so
`pd.DataFrame([item.raw for item in job.items])` works directly.

**Is there a free plan?**
Yes, see [pricing](https://product-mapper.com/pricing).

**Is there a Node.js version?**
Yes, [@siktec-lab/productmapper on npm](https://www.npmjs.com/package/@siktec-lab/productmapper)
([source](https://github.com/siktec-lab/product-mapper-ts)).

## Related

- [ProductMapper REST API documentation](https://product-mapper.com/docs)
- [MCP server for AI agents](https://product-mapper.com/docs/api-mcp)
- [Node.js and TypeScript SDK](https://github.com/siktec-lab/product-mapper-ts)
- [Report an issue](https://github.com/siktec-lab/product-mapper-py/issues)

## License

MIT, see [LICENSE](./LICENSE).
