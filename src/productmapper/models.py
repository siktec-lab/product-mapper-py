"""Typed models mirroring the ProductMapper REST API contract.

Every model is built with :meth:`from_dict`, which keeps only the documented fields as
attributes and stashes everything else in ``raw``. That way a new server-side field never
breaks an existing client, and you can always reach it through ``model.raw["newField"]``.

Attribute names are snake_case, the API sends camelCase, and the conversion happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "IDENTIFIER_TYPES",
    "REGIONS",
    "AmazonListing",
    "BatchItem",
    "BatchJob",
    "HistoryPage",
    "HistoryRow",
    "JobStatus",
    "ListingIdentifiers",
    "MappingResult",
    "QueuedLookup",
]

#: Identifier kinds the API accepts. "auto" lets the server infer from the value shape.
IDENTIFIER_TYPES = ("auto", "UPC", "EAN", "GTIN", "ASIN", "Title")

#: Amazon marketplace regions the resolution engine can search.
REGIONS = (
    "US",
    "CA",
    "MX",
    "BR",
    "UK",
    "DE",
    "FR",
    "IT",
    "ES",
    "NL",
    "PL",
    "SE",
    "IN",
    "JP",
    "AU",
    "SG",
)


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


@dataclass
class ListingIdentifiers:
    """Secondary identifiers Amazon reports for a listing.

    Not every provider returns these, so each field may be ``None``.
    """

    upc: str | None = None
    ean: str | None = None
    gtin: str | None = None
    asin: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ListingIdentifiers:
        return cls(
            upc=_as_str(data.get("upc")),
            ean=_as_str(data.get("ean")),
            gtin=_as_str(data.get("gtin")),
            asin=_as_str(data.get("asin")),
        )


@dataclass
class AmazonListing:
    """The full product and pricing data resolved for a matched Amazon listing.

    Nullable fields are genuinely ``None`` when Amazon does not report that data point
    for this listing, never a fabricated placeholder.
    """

    asin: str = ""
    title: str = ""
    brand: str = ""
    manufacturer: str | None = None
    description: str | None = None
    image_url: str | None = None
    price: float | None = None
    formatted_price: str | None = None
    list_price: float | None = None
    offer_count: int | None = None
    offer_count_fba: int | None = None
    offer_count_merchant: int | None = None
    is_buy_box_winner: bool | None = None
    sales_rank: int | None = None
    #: The more specific of the two classification levels a provider exposes.
    category: str | None = None
    #: The broader top-level department. Same as ``category`` when only one level exists.
    category_group: str | None = None
    package_quantity: int | None = None
    link: str | None = None
    is_active: bool | None = None
    identifiers: ListingIdentifiers | None = None
    #: The internal Amazon marketplace id (for example ATVPDKIKX0DER for US). Distinct from
    #: :attr:`MappingResult.marketplace_id`, which holds the matched product ASIN.
    marketplace_id: str | None = None
    #: Display label for :attr:`marketplace_id`, for example "US" or "CA".
    marketplace_label: str | None = None
    #: The untouched response object, including any field not listed above.
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AmazonListing:
        identifiers = data.get("identifiers")
        return cls(
            asin=_as_str(data.get("asin")) or "",
            title=_as_str(data.get("title")) or "",
            brand=_as_str(data.get("brand")) or "",
            manufacturer=_as_str(data.get("manufacturer")),
            description=_as_str(data.get("description")),
            image_url=_as_str(data.get("imageUrl")),
            price=_as_float(data.get("price")),
            formatted_price=_as_str(data.get("formattedPrice")),
            list_price=_as_float(data.get("listPrice")),
            offer_count=_as_int(data.get("offerCount")),
            offer_count_fba=_as_int(data.get("offerCountFba")),
            offer_count_merchant=_as_int(data.get("offerCountMerchant")),
            is_buy_box_winner=_as_bool(data.get("isBuyBoxWinner")),
            sales_rank=_as_int(data.get("salesRank")),
            category=_as_str(data.get("category")),
            category_group=_as_str(data.get("categoryGroup")),
            package_quantity=_as_int(data.get("packageQuantity")),
            link=_as_str(data.get("link")),
            is_active=_as_bool(data.get("isActive")),
            identifiers=(
                ListingIdentifiers.from_dict(identifiers) if isinstance(identifiers, dict) else None
            ),
            marketplace_id=_as_str(data.get("marketplaceId")),
            marketplace_label=_as_str(data.get("marketplaceLabel")),
            raw=data,
        )


@dataclass
class MappingResult:
    """A resolved single lookup."""

    identifier_type: str = ""
    identifier_value: str = ""
    marketplace: str = ""
    #: The matched product ASIN, despite the name. See :attr:`AmazonListing.marketplace_id`
    #: for the internal Amazon marketplace identifier.
    marketplace_id: str | None = None
    #: Amazon marketplace country this result matched in. ``None`` for not-found rows.
    amazon_marketplace_label: str | None = None
    #: Unix epoch milliseconds.
    timestamp: int | None = None
    listing_details: AmazonListing | None = None
    #: Only present when no region filter was given and the identifier matched in more than
    #: one Amazon marketplace region. The top-level fields always mirror ``results[0]``.
    results: list[MappingResult] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MappingResult:
        listing = data.get("listingDetails")
        nested = data.get("results")
        return cls(
            identifier_type=_as_str(data.get("identifierType")) or "",
            identifier_value=_as_str(data.get("identifierValue")) or "",
            marketplace=_as_str(data.get("marketplace")) or "",
            marketplace_id=_as_str(data.get("marketplaceId")),
            amazon_marketplace_label=_as_str(data.get("amazonMarketplaceLabel")),
            timestamp=_as_int(data.get("timestamp")),
            listing_details=(
                AmazonListing.from_dict(listing) if isinstance(listing, dict) else None
            ),
            results=(
                [cls.from_dict(item) for item in nested if isinstance(item, dict)]
                if isinstance(nested, list)
                else []
            ),
            raw=data,
        )

    @property
    def title(self) -> str | None:
        """Shortcut for ``listing_details.title``."""
        return self.listing_details.title if self.listing_details else None

    @property
    def price(self) -> float | None:
        """Shortcut for ``listing_details.price``."""
        return self.listing_details.price if self.listing_details else None

    @property
    def matches(self) -> list[MappingResult]:
        """Every regional match, as a list, even when the API returned only one."""
        return self.results or [self]


@dataclass
class QueuedLookup:
    """Returned by :meth:`ProductMapper.lookup` with ``poll=False`` while still resolving."""

    job_id: str
    status: str = "processing"
    message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueuedLookup:
        return cls(
            job_id=_as_str(data.get("jobId")) or "",
            status=_as_str(data.get("status")) or "processing",
            message=_as_str(data.get("message")),
            raw=data,
        )


@dataclass
class JobStatus:
    """The state of a queued single lookup.

    ``status`` is one of ``processing``, ``completed`` or ``failed``. ``data`` is set only
    when completed, ``error`` only when failed.
    """

    status: str = "processing"
    message: str | None = None
    data: MappingResult | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobStatus:
        payload = data.get("data")
        return cls(
            status=_as_str(data.get("status")) or "processing",
            message=_as_str(data.get("message")),
            data=(MappingResult.from_dict(payload) if isinstance(payload, dict) else None),
            error=_as_str(data.get("error")),
            raw=data,
        )

    @property
    def is_done(self) -> bool:
        """True once the job reached a terminal state."""
        return self.status in ("completed", "failed")


@dataclass
class BatchItem:
    """One row of a batch job.

    Deliberately a smaller field set than :class:`AmazonListing`: no link, is_active,
    category, identifiers, list_price or the full offer breakdown. Look an identifier up
    individually with :meth:`ProductMapper.lookup` when you need those.
    """

    id: str = ""
    identifier_type: str = ""
    identifier_value: str = ""
    marketplace_id: str | None = None
    title: str | None = None
    brand: str | None = None
    price: float | None = None
    formatted_price: str | None = None
    sales_rank: int | None = None
    offer_count: int | None = None
    image_url: str | None = None
    #: One of pending, completed, not_found, error.
    status: str = "pending"
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchItem:
        return cls(
            id=_as_str(data.get("id")) or "",
            identifier_type=_as_str(data.get("identifierType")) or "",
            identifier_value=_as_str(data.get("identifierValue")) or "",
            marketplace_id=_as_str(data.get("marketplaceId")),
            title=_as_str(data.get("title")),
            brand=_as_str(data.get("brand")),
            price=_as_float(data.get("price")),
            formatted_price=_as_str(data.get("formattedPrice")),
            sales_rank=_as_int(data.get("salesRank")),
            offer_count=_as_int(data.get("offerCount")),
            image_url=_as_str(data.get("imageUrl")),
            status=_as_str(data.get("status")) or "pending",
            error_message=_as_str(data.get("errorMessage")),
            raw=data,
        )


@dataclass
class BatchJob:
    """A batch job and, once processing has started, its items."""

    id: str = ""
    user_id: str = ""
    org_id: str | None = None
    marketplace: str = ""
    total_items: int = 0
    processed_items: int = 0
    matched_items: int = 0
    #: One of pending, processing, completed, failed.
    status: str = "pending"
    created_at: str | None = None
    updated_at: str | None = None
    #: Only populated once processing has started.
    items: list[BatchItem] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchJob:
        items = data.get("items")
        return cls(
            id=_as_str(data.get("id")) or "",
            user_id=_as_str(data.get("userId")) or "",
            org_id=_as_str(data.get("orgId")),
            marketplace=_as_str(data.get("marketplace")) or "",
            total_items=_as_int(data.get("totalItems")) or 0,
            processed_items=_as_int(data.get("processedItems")) or 0,
            matched_items=_as_int(data.get("matchedItems")) or 0,
            status=_as_str(data.get("status")) or "pending",
            created_at=_as_str(data.get("createdAt")),
            updated_at=_as_str(data.get("updatedAt")),
            items=(
                [BatchItem.from_dict(item) for item in items if isinstance(item, dict)]
                if isinstance(items, list)
                else []
            ),
            raw=data,
        )

    @property
    def is_done(self) -> bool:
        """True once the batch reached a terminal state."""
        return self.status in ("completed", "failed")

    @property
    def progress(self) -> float:
        """Fraction of items processed, from 0.0 to 1.0."""
        if self.total_items <= 0:
            return 0.0
        return self.processed_items / self.total_items


@dataclass
class HistoryRow:
    """One row of your lookup history."""

    id: str = ""
    identifier_type: str = ""
    identifier_value: str = ""
    marketplace: str = ""
    marketplace_id: str | None = None
    title: str | None = None
    brand: str | None = None
    price: float | None = None
    formatted_price: str | None = None
    image_url: str | None = None
    status: str = ""
    created_at: str | None = None
    #: How many times you have looked up this exact identifier.
    seen_count: int | None = None
    last_seen_at: str | None = None
    listing_details: AmazonListing | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryRow:
        listing = data.get("listingDetails")
        return cls(
            id=_as_str(data.get("id")) or "",
            identifier_type=_as_str(data.get("identifierType")) or "",
            identifier_value=_as_str(data.get("identifierValue")) or "",
            marketplace=_as_str(data.get("marketplace")) or "",
            marketplace_id=_as_str(data.get("marketplaceId")),
            title=_as_str(data.get("title")),
            brand=_as_str(data.get("brand")),
            price=_as_float(data.get("price")),
            formatted_price=_as_str(data.get("formattedPrice")),
            image_url=_as_str(data.get("imageUrl")),
            status=_as_str(data.get("status")) or "",
            created_at=_as_str(data.get("createdAt")),
            seen_count=_as_int(data.get("seenCount")),
            last_seen_at=_as_str(data.get("lastSeenAt")),
            listing_details=(
                AmazonListing.from_dict(listing) if isinstance(listing, dict) else None
            ),
            raw=data,
        )


@dataclass
class HistoryPage:
    """A page of lookup history. Iterate the page to walk its rows."""

    history: list[HistoryRow] = field(default_factory=list)
    page: int = 1
    page_size: int = 25
    total: int = 0
    total_pages: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryPage:
        rows = data.get("history")
        return cls(
            history=(
                [HistoryRow.from_dict(row) for row in rows if isinstance(row, dict)]
                if isinstance(rows, list)
                else []
            ),
            page=_as_int(data.get("page")) or 1,
            page_size=_as_int(data.get("pageSize")) or 25,
            total=_as_int(data.get("total")) or 0,
            total_pages=_as_int(data.get("totalPages")) or 0,
            raw=data,
        )

    def __iter__(self) -> Any:
        return iter(self.history)

    def __len__(self) -> int:
        return len(self.history)
