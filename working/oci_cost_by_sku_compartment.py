#!/usr/bin/env python3
"""Report monthly OCI SKU cost and usage by compartment as CSV.

Examples:
  python working/oci_cost_by_sku_compartment.py --sku B12345
  python working/oci_cost_by_sku_compartment.py --sku B12345 -p MY_PROFILE --csv costs.csv
  python working/oci_cost_by_sku_compartment.py --sku B12345 --month 2026-10
  python working/oci_cost_by_sku_compartment.py --sku B12345 -p MY_PROFILE --ytd --csv ytd.csv

Requires the OCI SDK and permission to read usage-report in tenancy.
"""

from __future__ import annotations

import argparse
import csv
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import TextIO

import oci
from oci.usage_api.models import Dimension, Filter, RequestSummarizedUsagesDetails


COLUMNS = [
    "month", "sku_part_number", "service", "compartment_id", "compartment_name", "resource_id",
    "unit", "currency", "usage_quantity", "cost", "effective_unit_cost",
    "api_unit_price",
]


def month_bounds(month: str | None = None, now: datetime | None = None):
    """Return UTC calendar-month boundaries, with an exclusive end."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if month is None:
        end = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (end - timedelta(days=1)).replace(day=1)
    else:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        if start.strftime("%Y-%m") != month:
            raise ValueError("Month must use YYYY-MM format")
        end = (start + timedelta(days=32)).replace(day=1)
        if end > current.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
            raise ValueError("Choose a completed calendar month")
    return start, end


def fetch_rows(client, tenancy_id: str, sku: str, start: datetime, end: datetime,
               *, partial_month: bool = False):
    """Fetch monthly resource costs for one SKU, retaining service attribution.

    COST automatically groups by currency; include unit explicitly so both
    computed_amount and computed_quantity are meaningful. The four explicit
    groups are compartment, service, resource, and unit; SKU is fixed by filter.
    Compartment names are retrieved with a separate Usage API query, avoiding
    an Identity API permission requirement or grouping by non-unique names.
    """
    request = RequestSummarizedUsagesDetails(
        tenant_id=tenancy_id,
        time_usage_started=start,
        time_usage_ended=end,
        granularity="DAILY" if partial_month else "MONTHLY",
        query_type="COST",
        is_aggregate_by_time=partial_month,
        compartment_depth=6,
        group_by=["compartmentId", "service", "resourceId", "unit"],
        filter=Filter(
            operator="AND",
            dimensions=[Dimension(key="skuPartNumber", value=sku)],
        ),
    )
    rows = []
    for item in usage_items(client, request):
        quantity = (
            Decimal(str(item.computed_quantity))
            if item.computed_quantity is not None else None
        )
        cost = Decimal(str(item.computed_amount)) if item.computed_amount is not None else None
        effective = cost / quantity if cost is not None and quantity else None
        rows.append({
            "month": (start if partial_month else item.time_usage_started).strftime("%Y-%m"),
            "sku_part_number": sku,
            "service": item.service,
            "compartment_id": item.compartment_id,
            "compartment_name": None,
            "resource_id": item.resource_id,
            "unit": item.unit,
            "currency": item.currency,
            "usage_quantity": quantity,
            "cost": cost,
            "effective_unit_cost": effective,
            "api_unit_price": item.unit_price,
        })
    if rows:
        names_request = deepcopy(request)
        names_request.group_by = ["compartmentId", "compartmentName"]
        names_request.is_aggregate_by_time = True
        names = {}
        for item in usage_items(client, names_request):
            names.setdefault(item.compartment_id, set()).add(item.compartment_name or "")
        for row in rows:
            # If billing history has multiple names for an OCID, retain them
            # deterministically instead of selecting an arbitrary page's name.
            row["compartment_name"] = " | ".join(sorted(names.get(row["compartment_id"], set())))
    return rows


def usage_items(client, request):
    """Iterate all pages for either the cost breakdown or name lookup."""
    page = None
    while True:
        response = client.request_summarized_usages(request, page=page)
        yield from response.data.items
        page = response.next_page
        if not page:
            break


def report_rows(client, tenancy_id: str, sku: str, start: datetime, end: datetime):
    """Keep monthly buckets and query an unfinished month at daily granularity.

    The API requires MONTHLY boundaries on the first of a month. A separate
    DAILY query aggregates the current month's completed UTC days into one row
    per compartment/service/resource/unit/currency. All queries paginate independently.
    """
    rows = []
    month_start = end.replace(day=1)
    if start < month_start:
        rows.extend(fetch_rows(client, tenancy_id, sku, start, month_start))
    if month_start < end:
        rows.extend(fetch_rows(client, tenancy_id, sku, month_start, end, partial_month=True))
    return sorted(rows, key=lambda row: tuple(
        str(row[key] or "") for key in
        ("compartment_name", "compartment_id", "month", "service", "resource_id", "currency", "unit")
    ))


def report_bounds(month: str | None = None, ytd: bool = False,
                  now: datetime | None = None):
    """YTD ends at today's UTC midnight, excluding today's incomplete usage."""
    if not ytd:
        return month_bounds(month, now)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return end.replace(month=1, day=1), end


def write_csv(rows: list[dict], stream: TextIO):
    """Write a header even if there are no matches; None becomes an empty cell."""
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    """Run the report using an OCI config profile or instance principal."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sku", required=True, help="Exact SKU part number, e.g. B12345.")
    period = parser.add_mutually_exclusive_group()
    period.add_argument("--month", help="Completed month as YYYY-MM. Default: last complete month in UTC.")
    period.add_argument("--ytd", action="store_true", help="January 1 through yesterday UTC, broken down monthly.")
    parser.add_argument("-p", "--profile", default="DEFAULT", help="OCI config profile (default: DEFAULT).")
    parser.add_argument("--config-file", default=oci.config.DEFAULT_LOCATION, help="OCI config file.")
    parser.add_argument("--instance-principal", action="store_true", help="Authenticate as an OCI instance.")
    parser.add_argument("--region", help="Override the configured OCI region.")
    parser.add_argument("--csv", type=Path, help="Write CSV to this file instead of stdout.")
    args = parser.parse_args()
    sku = args.sku.strip()
    if not sku:
        parser.error("--sku must not be empty")
    try:
        start, end = report_bounds(args.month, args.ytd)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        client_args = {"retry_strategy": oci.retry.DEFAULT_RETRY_STRATEGY, "timeout": (10, 600)}
        if args.instance_principal:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            config = {"region": args.region or signer.region}
            client_args["signer"] = signer
            tenancy_id = signer.tenancy_id
        else:
            config = oci.config.from_file(file_location=args.config_file, profile_name=args.profile)
            if args.region:
                config["region"] = args.region
            tenancy_id = config["tenancy"]
        client = oci.usage_api.UsageapiClient(config, **client_args)
        print(f"Querying SKU {sku}: {start:%Y-%m-%d} to {end:%Y-%m-%d} UTC (end exclusive)", file=sys.stderr)
        rows = report_rows(client, tenancy_id, sku, start, end)
        if args.csv:
            with args.csv.open("w", encoding="utf-8", newline="") as stream:
                write_csv(rows, stream)
        else:
            write_csv(rows, sys.stdout)
        compartments = len({row["compartment_id"] for row in rows})
        print(f"Returned {len(rows)} row(s) across {compartments} compartment(s)." if rows
              else "No matching usage found for this SKU and period.", file=sys.stderr)
        return 0
    except (oci.exceptions.ServiceError, oci.exceptions.ClientError,
            oci.exceptions.RequestException, oci.exceptions.ConfigFileNotFound,
            oci.exceptions.ProfileNotFound, oci.exceptions.InvalidConfig, OSError) as exc:
        print(f"Report failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
