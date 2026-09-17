"""Official Python client for the ProductMapper API.

Resolve a UPC, EAN, GTIN, ASIN or free-text title into a live Amazon catalog listing.

    from productmapper import ProductMapper

    client = ProductMapper(api_key="pm_live_...")
    result = client.lookup(value="079361039905", type="UPC")
    print(result.title, result.price)

See https://product-mapper.com/docs for the full API reference.
"""

from .client import DEFAULT_BASE_URL, AsyncProductMapper, ProductMapper
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    CreditsExhaustedError,
    JobFailedError,
    NotFoundError,
    PermissionError,
    ProductMapperError,
    RateLimitError,
    ServerError,
    TimeoutError,
    ValidationError,
)
from .models import (
    IDENTIFIER_TYPES,
    REGIONS,
    AmazonListing,
    BatchItem,
    BatchJob,
    HistoryPage,
    HistoryRow,
    JobStatus,
    ListingIdentifiers,
    MappingResult,
    QueuedLookup,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_BASE_URL",
    "IDENTIFIER_TYPES",
    "REGIONS",
    "AmazonListing",
    "AsyncProductMapper",
    "AuthenticationError",
    "BatchItem",
    "BatchJob",
    "ConnectionError",
    "CreditsExhaustedError",
    "HistoryPage",
    "HistoryRow",
    "JobFailedError",
    "JobStatus",
    "ListingIdentifiers",
    "MappingResult",
    "NotFoundError",
    "PermissionError",
    "ProductMapper",
    "ProductMapperError",
    "QueuedLookup",
    "RateLimitError",
    "ServerError",
    "TimeoutError",
    "ValidationError",
    "__version__",
]
