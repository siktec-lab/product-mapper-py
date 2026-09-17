"""Resolve one identifier into an Amazon listing.

Run with: PRODUCTMAPPER_API_KEY=pm_live_... python examples/single_lookup.py
"""

import os

from productmapper import CreditsExhaustedError, NotFoundError, ProductMapper


def main() -> None:
    with ProductMapper(api_key=os.environ["PRODUCTMAPPER_API_KEY"]) as client:
        try:
            result = client.lookup(value="079361039905", type="UPC")
        except NotFoundError:
            print("No match in the Amazon catalog for that identifier.")
            return
        except CreditsExhaustedError:
            print("Out of credits. Top up at https://product-mapper.com/dashboard/billing")
            return

        listing = result.listing_details
        print("ASIN:      ", result.marketplace_id)
        print("Title:     ", listing.title if listing else None)
        print("Brand:     ", listing.brand if listing else None)
        print("Price:     ", listing.formatted_price if listing else "not reported")
        print("Sales rank:", listing.sales_rank if listing else "not reported")
        print("Region:    ", result.amazon_marketplace_label)
        print("Link:      ", listing.link if listing else None)


if __name__ == "__main__":
    main()
