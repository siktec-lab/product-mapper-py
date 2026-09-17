"""Page through your lookup history, and search it.

Run with: PRODUCTMAPPER_API_KEY=pm_live_... python examples/history.py
"""

import os

from productmapper import ProductMapper


def main() -> None:
    with ProductMapper(api_key=os.environ["PRODUCTMAPPER_API_KEY"]) as client:
        first_page = client.history(page=1)
        print(f"{first_page.total} rows across {first_page.total_pages} pages\n")

        for row in first_page:
            print(f"  {row.created_at}  {row.identifier_value:<20} {row.title or row.status}")

        matches = client.history(search="coffee")
        print(f'\n{matches.total} rows match "coffee"')

        # history_all walks every page for you, one row at a time.
        counted = sum(1 for _ in client.history_all())
        print(f"Walked {counted} rows in total")


if __name__ == "__main__":
    main()
