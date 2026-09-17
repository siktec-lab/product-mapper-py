"""Submit a batch of identifiers, follow its progress, then export the results as CSV.

Run with: PRODUCTMAPPER_API_KEY=pm_live_... python examples/batch_lookup.py
"""

import os
from pathlib import Path

from productmapper import BatchJob, ProductMapper


def show_progress(job: BatchJob) -> None:
    print(f"  {job.processed_items}/{job.total_items} processed")


def main() -> None:
    identifiers = [
        "079361039905",
        "B004U9VVX6",
        "0885909950805",
        "Logitech MX Master 3S",
    ]

    with ProductMapper(api_key=os.environ["PRODUCTMAPPER_API_KEY"]) as client:
        job = client.lookup_many(identifiers)
        print(f"Submitted batch {job.id} with {job.total_items} items")

        finished = client.wait_for_batch(job.id, on_progress=show_progress)

        print(f"\nMatched {finished.matched_items} of {finished.total_items}\n")
        for item in finished.items:
            label = item.title or item.status
            print(f"  {item.identifier_value:<24} {label}")

        csv_text = client.get_batch_csv(job.id)
        Path("batch-results.csv").write_text(csv_text, encoding="utf-8")
        print("\nSaved batch-results.csv")


if __name__ == "__main__":
    main()
