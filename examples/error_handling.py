"""Every exception this client raises, and how to react to each one.

Note that PermissionError, TimeoutError and ConnectionError deliberately shadow the
builtins of the same name, so import them from productmapper as done here.

Run with: PRODUCTMAPPER_API_KEY=pm_live_... python examples/error_handling.py
"""

import os

from productmapper import (
    AuthenticationError,
    ConnectionError,
    CreditsExhaustedError,
    JobFailedError,
    NotFoundError,
    PermissionError,
    ProductMapper,
    ProductMapperError,
    RateLimitError,
    ServerError,
    TimeoutError,
    ValidationError,
)


def main() -> None:
    client = ProductMapper(
        api_key=os.environ["PRODUCTMAPPER_API_KEY"],
        # Rate limits, 5xx responses and network blips are retried automatically.
        max_retries=3,
        timeout=20.0,
    )

    try:
        result = client.lookup(value="079361039905", type="UPC", region="US")
        print("Matched:", result.title)
    except ValidationError as exc:
        print("The request was rejected:", exc.message)
    except AuthenticationError:
        print("Check PRODUCTMAPPER_API_KEY, it was rejected.")
    except CreditsExhaustedError:
        print("Out of credits. Upgrade or buy a credit pack.")
    except PermissionError:
        print("No active organization selected for this key.")
    except NotFoundError:
        print("No match in the Amazon catalog.")
    except RateLimitError as exc:
        print(f"Rate limited. Retry after {exc.retry_after}s (limit {exc.limit}/min).")
    except JobFailedError as exc:
        print(f"Job {exc.job_id} failed: {exc.message}")
    except TimeoutError:
        print("The request took too long.")
    except ConnectionError:
        print("Could not reach the API.")
    except ServerError as exc:
        print("The API failed to handle the request:", exc.status)
    except ProductMapperError as exc:
        # Base class, so one except can cover everything above.
        print(f"Unexpected API error {exc.status}: {exc.message}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
