"""The async client, including resolving many identifiers concurrently.

Run with: PRODUCTMAPPER_API_KEY=pm_live_... python examples/async_lookup.py
"""

import asyncio
import os

from productmapper import AsyncProductMapper, ProductMapperError


async def main() -> None:
    async with AsyncProductMapper(api_key=os.environ["PRODUCTMAPPER_API_KEY"]) as client:
        result = await client.lookup(value="079361039905", type="UPC")
        print(result.title, result.price)

        # Several lookups at once. return_exceptions keeps one failure from
        # cancelling the rest, so a not-found identifier does not lose the others.
        identifiers = ["079361039905", "B004U9VVX6", "0885909950805"]
        results = await asyncio.gather(
            *(client.lookup(value=value) for value in identifiers),
            return_exceptions=True,
        )

        print()
        for value, outcome in zip(identifiers, results):
            if isinstance(outcome, ProductMapperError):
                print(f"  {value:<20} failed: {outcome}")
            elif isinstance(outcome, BaseException):
                raise outcome
            else:
                print(f"  {value:<20} {outcome.title}")

        print()
        async for row in client.history_all():
            print(f"  {row.identifier_value:<20} {row.title or row.status}")


if __name__ == "__main__":
    asyncio.run(main())
