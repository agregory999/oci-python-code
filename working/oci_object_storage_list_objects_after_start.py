#!/usr/bin/env python3
"""List OCI Object Storage objects starting at a given prefix/path using lexicographic `start`.

This script is meant to help you understand how the Object Storage `start` parameter
for `list_objects` behaves with full object paths (including pseudo-directories).

It will:
  * Use your ~/.oci/config profile
  * Call list_objects with the provided `start` value
  * Paginate through all results using the OCI Python SDK paginator
  * Print object name and creation time, sorted descending by object name

Usage examples:

  python3 oci-objects-after-start.py \
      --profile DEFAULT \
      --namespace mynamespace \
      --bucket my-bucket \
      --start path/to/object-prefix

You can use full object names or any lexicographic starting point in `--start`.
"""

import argparse
import sys
from datetime import datetime
from typing import List, Tuple

import oci


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List OCI Object Storage objects whose names are lexicographically "
            "greater than or equal to the given start value."
        )
    )

    parser.add_argument(
        "--profile",
        "-p",
        default="DEFAULT",
        help="OCI CLI profile name from ~/.oci/config (default: DEFAULT)",
    )

    parser.add_argument(
        "--namespace",
        "-n",
        required=True,
        help="Object Storage namespace name",
    )

    parser.add_argument(
        "--bucket",
        "-b",
        required=True,
        help="Object Storage bucket name",
    )

    parser.add_argument(
        "--start",
        "-s",
        required=True,
        help=(
            "Value for list_objects 'start' parameter. Objects with names "
            "lexicographically >= this value will be returned. This can be a "
            "full object path or any string prefix."
        ),
    )

    parser.add_argument(
        "--end",
        "-e",
        required=False,
        help=(
            "Optional upper bound (exclusive) on object names. After fetching all "
            "objects using 'start', the script will keep only those with names "
            "lexicographically < this value. This is a client-side filter to "
            "let you experiment with a start/end range."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Optional maximum number of objects to display (after sorting). "
            "If omitted, all objects are shown."
        ),
    )

    return parser.parse_args()


def get_object_storage_client(profile: str) -> oci.object_storage.ObjectStorageClient:
    """Initialize and return OCI Object Storage client using a config profile."""

    try:
        config = oci.config.from_file(profile_name=profile)
    except Exception as e:  # noqa: BLE001
        print(f"Error loading OCI config for profile '{profile}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        client = oci.object_storage.ObjectStorageClient(config)
    except Exception as e:  # noqa: BLE001
        print(f"Error creating ObjectStorageClient: {e}", file=sys.stderr)
        sys.exit(1)

    return client


def list_objects_from_start(
    client: oci.object_storage.ObjectStorageClient,
    namespace: str,
    bucket: str,
    start: str,
    end: str | None = None,
) -> List[Tuple[str, datetime | None]]:
    """Return list of (object_name, time_created) for objects >= `start`.

    Uses the OCI pagination helper `list_call_get_all_results`, which returns
    a single response object whose `.data` field is an ObjectSummaryCollection
    containing all ObjectSummary items across all pages.
    """

    # This mirrors your working pattern:
    #   objects = oci.pagination.list_call_get_all_results(
    #       object_storage.list_objects,
    #       ns, bucket,
    #       fields="timeCreated,size",
    #       prefix="reports/cost-csv/",
    #       start=...
    #   ).data

    response = oci.pagination.list_call_get_all_results(
        client.list_objects,
        namespace,
        bucket,
        start=start,
        fields="timeCreated",
    )

    collection = response.data

    results: List[Tuple[str, datetime | None]] = []

    for obj in collection.objects:
        # obj is an ObjectSummary instance
        name = obj.name

        # If an end bound is provided, apply a client-side lexicographic filter
        # so that only start <= name < end are kept. This mimics a half-open
        # interval [start, end) on object names.
        if end is not None and name >= end:
            continue

        results.append((name, obj.time_created))

    # Sort by object name descending so you can visually compare lexicographic order
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def main() -> None:
    args = parse_args()

    client = get_object_storage_client(args.profile)

    print(
        f"Listing objects in namespace='{args.namespace}', bucket='{args.bucket}' "
        f"with start>='{args.start}' (lexicographic)"
        + (f" and end<'{args.end}'" if args.end else ""),
        file=sys.stderr,
    )

    objects = list_objects_from_start(
        client,
        args.namespace,
        args.bucket,
        args.start,
        end=args.end,
    )

    if args.limit is not None:
        objects = objects[: args.limit]

    if not objects:
        print("No objects returned.")
        return

    # Print header
    print(f"{'OBJECT NAME':<80}  {'TIME CREATED'}")
    print("-" * 120)

    for name, created in objects:
        created_str = created.isoformat() if created is not None else "-"
        print(f"{name:<80}  {created_str}")


if __name__ == "__main__":
    main()
