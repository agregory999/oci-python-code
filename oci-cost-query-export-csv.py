#!/usr/bin/env python3
"""OCI cost query to CSV exporter.

Examples:
  python oci-cost-query-export-csv.py
  python oci-cost-query-export-csv.py --days-back 7 --granularity DAILY --group-by service
  python oci-cost-query-export-csv.py --days-back 30 --group-by service --group-by skuName
  python oci-cost-query-export-csv.py --mtd --dimension-filter service=COMPUTE
  python oci-cost-query-export-csv.py --start 2026-05-01 --end 2026-06-01 --granularity DAILY \
    --tag-filter Operations.CostCenter=ENG --csv may_costs.csv
  python oci-cost-query-export-csv.py --start 2026-05-01T00:00:00Z --end 2026-05-08T00:00:00Z \
    --filter-operator OR --dimension-filter service=COMPUTE --dimension-filter service=BLOCK_STORAGE
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import oci
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, RequestException, ServiceError
from oci.usage_api import UsageapiClient
from oci.usage_api.models import Dimension, Filter, RequestSummarizedUsagesDetails, Tag
from oci.util import to_dict


DEFAULT_GROUP_BY = ["service", "skuName"]
DEFAULT_DAYS_BACK = 7
PREFERRED_CSV_COLUMNS = [
    "time_usage_started",
    "time_usage_ended",
    "service",
    "sku_name",
    "resource_id",
    "compartment_name",
    "region",
    "availability_domain",
    "computed_amount",
    "currency",
    "unit",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI options.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Query OCI Usage API for cost data and export results to CSV. "
            "Time range can be provided explicitly or derived with --days-back/--mtd."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--profile",
        default="DEFAULT",
        help="OCI CLI config profile name when using config-file auth. Default: %(default)s",
    )
    parser.add_argument(
        "--instance-principal",
        action="store_true",
        help="Use OCI Instance Principal auth (ignores --profile).",
    )
    parser.add_argument(
        "--region",
        help="Optional region override when using --instance-principal, e.g. us-ashburn-1.",
    )
    parser.add_argument(
        "--start",
        help=(
            "Start timestamp in UTC. Supports YYYY-MM-DD or ISO8601 "
            "(example: 2026-05-01 or 2026-05-01T00:00:00Z)."
        ),
    )
    parser.add_argument(
        "--end",
        help=(
            "End timestamp in UTC (exclusive). Supports YYYY-MM-DD or ISO8601 "
            "(example: 2026-06-01 or 2026-06-01T00:00:00Z)."
        ),
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=DEFAULT_DAYS_BACK,
        help=f"Relative range when --start/--end are not used. Default: {DEFAULT_DAYS_BACK}",
    )
    parser.add_argument(
        "--mtd",
        action="store_true",
        help="Use month-to-date in UTC (first day of current month to now).",
    )
    parser.add_argument(
        "-g",
        "--granularity",
        choices=["HOURLY", "DAILY", "MONTHLY"],
        default="DAILY",
        help="Aggregation level for OCI Usage API. Default: %(default)s",
    )
    parser.add_argument(
        "--aggregate-by-time",
        action="store_true",
        help=(
            "Aggregate over the full time range (summary per group). "
            "Default is False, which keeps time-sliced rows based on granularity."
        ),
    )
    parser.add_argument(
        "--group-by",
        action="append",
        help=(
            "Repeatable Usage API grouping field (example: --group-by service --group-by skuName). "
            "Defaults to service + skuName."
        ),
    )
    parser.add_argument(
        "--dimension-filter",
        action="append",
        help=(
            "Repeatable dimension filter as key=value (example: service=COMPUTE, "
            "resourceId=ocid1.instance...)."
        ),
    )
    parser.add_argument(
        "--tag-filter",
        action="append",
        help=(
            "Repeatable tag filter as namespace.key=value "
            "(example: Operations.CostCenter=ENG)."
        ),
    )
    parser.add_argument(
        "--filter-operator",
        choices=["AND", "OR"],
        default="AND",
        help="How multiple filters are combined. Default: %(default)s",
    )
    parser.add_argument(
        "--compartment-depth",
        type=int,
        default=6,
        help="Compartment depth used by Usage API query. Default: %(default)s",
    )
    parser.add_argument(
        "--csv",
        help="Output CSV filename. Default: auto-generated timestamped filename.",
    )
    parser.add_argument(
        "--drop-empty-columns",
        action="store_true",
        help="Remove columns that are empty for every returned row.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def setup_logging(verbose: bool) -> logging.Logger:
    """Configure and return a module logger.

    Args:
        verbose: Whether debug logging should be enabled.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger(__name__)


def parse_utc_datetime(value: str) -> datetime:
    """Parse a date or datetime string into UTC datetime.

    Args:
        value: Input date in YYYY-MM-DD or ISO8601 form.

    Returns:
        datetime: Timezone-aware UTC datetime.

    Raises:
        ValueError: If the value cannot be parsed.
    """
    try:
        if len(value) == 10:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return parsed.replace(tzinfo=timezone.utc)
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"Invalid datetime '{value}'. Use YYYY-MM-DD or ISO8601 (example: 2026-05-01T00:00:00Z)."
        ) from exc


def normalize_datetime_for_granularity(value: datetime, granularity: str) -> datetime:
    """Normalize datetime precision to match OCI Usage API granularity requirements.

    Args:
        value: Input UTC datetime.
        granularity: Query granularity (HOURLY, DAILY, MONTHLY).

    Returns:
        datetime: Normalized UTC datetime.
    """
    if granularity in {"DAILY", "MONTHLY"}:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(minute=0, second=0, microsecond=0)


def resolve_time_range(args: argparse.Namespace, logger: logging.Logger) -> Tuple[datetime, datetime]:
    """Resolve the query time range from CLI options.

    Args:
        args: Parsed command-line options.
        logger: Logger for status output.

    Returns:
        tuple[datetime, datetime]: Start and end UTC datetimes.

    Raises:
        ValueError: If time range arguments are invalid.
    """
    now_utc = datetime.now(timezone.utc)
    has_explicit_start_end = bool(args.start or args.end)
    if has_explicit_start_end and args.mtd:
        raise ValueError("Use either --start/--end or --mtd, not both.")

    if has_explicit_start_end:
        if not (args.start and args.end):
            raise ValueError("Both --start and --end are required when either is provided.")
        start = parse_utc_datetime(args.start)
        end = parse_utc_datetime(args.end)
        mode = "explicit --start/--end"
    elif args.mtd:
        start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now_utc
        mode = "--mtd"
    else:
        if args.days_back < 1:
            raise ValueError("--days-back must be greater than 0.")
        end = now_utc
        start = now_utc - timedelta(days=args.days_back)
        mode = f"--days-back {args.days_back}"

    start = normalize_datetime_for_granularity(start, args.granularity)
    end = normalize_datetime_for_granularity(end, args.granularity)

    if end <= start:
        raise ValueError(f"Time range invalid: end ({end.isoformat()}) must be after start ({start.isoformat()}).")

    logger.info("Time selection mode: %s", mode)
    logger.info("Time range UTC: %s to %s", start.isoformat(), end.isoformat())
    return start, end


def parse_dimension_filters(dimension_filters: Sequence[str] | None) -> List[Dimension]:
    """Parse CLI dimension filters into OCI Dimension models.

    Args:
        dimension_filters: Repeated key=value strings.

    Returns:
        list[Dimension]: Parsed dimensions.

    Raises:
        ValueError: If any filter is malformed.
    """
    if not dimension_filters:
        return []

    dimensions: List[Dimension] = []
    for expression in dimension_filters:
        if "=" not in expression:
            raise ValueError(f"Invalid --dimension-filter '{expression}'. Expected key=value.")
        key, value = expression.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"Invalid --dimension-filter '{expression}'. Expected key=value.")
        dimensions.append(Dimension(key=key, value=value))
    return dimensions


def parse_tag_filters(tag_filters: Sequence[str] | None) -> List[Tag]:
    """Parse CLI tag filters into OCI Tag models.

    Args:
        tag_filters: Repeated namespace.key=value strings.

    Returns:
        list[Tag]: Parsed tags.

    Raises:
        ValueError: If any tag filter is malformed.
    """
    if not tag_filters:
        return []

    tags: List[Tag] = []
    for expression in tag_filters:
        if "=" not in expression:
            raise ValueError(f"Invalid --tag-filter '{expression}'. Expected namespace.key=value.")
        key_expr, value = expression.split("=", 1)
        if "." not in key_expr:
            raise ValueError(f"Invalid --tag-filter '{expression}'. Expected namespace.key=value.")
        namespace, key = key_expr.split(".", 1)
        namespace = namespace.strip()
        key = key.strip()
        value = value.strip()
        if not namespace or not key or not value:
            raise ValueError(f"Invalid --tag-filter '{expression}'. Expected namespace.key=value.")
        tags.append(Tag(namespace=namespace, key=key, value=value))
    return tags


def build_filter(args: argparse.Namespace) -> Filter | None:
    """Build an optional OCI Usage API filter from CLI options.

    Args:
        args: Parsed command-line options.

    Returns:
        Filter | None: Usage API filter or None when no filter was requested.
    """
    dimensions = parse_dimension_filters(args.dimension_filter)
    tags = parse_tag_filters(args.tag_filter)
    if not dimensions and not tags:
        return None
    return Filter(
        operator=args.filter_operator,
        dimensions=dimensions if dimensions else None,
        tags=tags if tags else None,
    )


def get_usage_client(args: argparse.Namespace, logger: logging.Logger) -> Tuple[UsageapiClient, str]:
    """Create an OCI Usage API client and return it with tenancy OCID.

    Args:
        args: Parsed command-line options.
        logger: Logger for status output.

    Returns:
        tuple[UsageapiClient, str]: Usage API client and tenancy OCID.
    """
    try:
        if args.instance_principal:
            signer = InstancePrincipalsSecurityTokenSigner()
            client_config: Dict[str, str] = {}
            if args.region:
                client_config["region"] = args.region
            tenancy_id = signer.tenancy_id
            logger.info("Auth mode: Instance Principal")
            client = UsageapiClient(
                config=client_config,
                signer=signer,
                retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
                timeout=600,
            )
            return client, tenancy_id

        config_data = oci.config.from_file(profile_name=args.profile)
        tenancy_id = config_data["tenancy"]
        logger.info("Auth mode: config file profile '%s'", args.profile)
        client = UsageapiClient(
            config=config_data,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
            timeout=600,
        )
        return client, tenancy_id
    except ClientError as exc:
        raise RuntimeError(f"Failed to initialize OCI client: {exc}") from exc


def fetch_cost_rows(
    client: UsageapiClient,
    tenancy_id: str,
    start: datetime,
    end: datetime,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    """Fetch paginated cost usage rows from OCI Usage API.

    Args:
        client: Initialized OCI Usage API client.
        tenancy_id: Tenancy OCID.
        start: Query start datetime in UTC.
        end: Query end datetime in UTC.
        args: Parsed command-line options.
        logger: Logger for status output.

    Returns:
        list[dict[str, Any]]: Flattened rows suitable for CSV output.
    """
    group_by = args.group_by if args.group_by else DEFAULT_GROUP_BY
    query_filter = build_filter(args)
    request = RequestSummarizedUsagesDetails(
        tenant_id=tenancy_id,
        query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_COST,
        compartment_depth=float(args.compartment_depth),
        time_usage_started=start,
        time_usage_ended=end,
        is_aggregate_by_time=args.aggregate_by_time,
        granularity=args.granularity,
        group_by=group_by,
        filter=query_filter,
    )

    logger.info("Granularity: %s", args.granularity)
    logger.info("Aggregate by time: %s", args.aggregate_by_time)
    logger.info("Group by: %s", ", ".join(group_by))
    if query_filter:
        logger.info("Filters enabled (operator=%s)", args.filter_operator)

    rows: List[Dict[str, Any]] = []
    backfilled_time_rows = 0
    page = None
    while True:
        response = client.request_summarized_usages(
            request_summarized_usages_details=request,
            page=page,
        )
        for item in response.data.items:
            record = to_dict(item)
            normalized = normalize_usage_row(record, start, end)
            if normalized.pop("_time_backfilled", False):
                backfilled_time_rows += 1
            rows.append(normalized)
        page = response.next_page
        if not page:
            break

    if backfilled_time_rows:
        logger.warning(
            "Backfilled time_usage_started/time_usage_ended using query bounds for %d row(s).",
            backfilled_time_rows,
        )
    return rows


def normalize_usage_row(record: Dict[str, Any], start: datetime, end: datetime) -> Dict[str, Any]:
    """Normalize a UsageSummary row into CSV-friendly values.

    Args:
        record: Raw row dictionary converted from OCI UsageSummary.
        start: Query start datetime in UTC.
        end: Query end datetime in UTC.

    Returns:
        dict[str, Any]: Normalized row ready for CSV writing.
    """
    normalized: Dict[str, Any] = {}
    for key, value in record.items():
        normalized[key] = normalize_field_value(key, value)

    backfilled = False
    if not normalized.get("time_usage_started"):
        normalized["time_usage_started"] = start.isoformat()
        backfilled = True
    if not normalized.get("time_usage_ended"):
        normalized["time_usage_ended"] = end.isoformat()
        backfilled = True
    if backfilled:
        normalized["_time_backfilled"] = True
    return normalized


def normalize_field_value(key: str, value: Any) -> Any:
    """Normalize field value for CSV output.

    Args:
        key: Field name.
        value: Field value.

    Returns:
        Any: Scalar or serialized value suitable for CSV.
    """
    if key == "tags" and is_placeholder_tags(value):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def is_placeholder_tags(value: Any) -> bool:
    """Check whether tags value is OCI's null placeholder list.

    Args:
        value: Value from the `tags` field.

    Returns:
        bool: True when the value contains only null tag objects.
    """
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        if any(item.get(field) is not None for field in ("namespace", "key", "value")):
            return False
    return True


def drop_empty_columns(rows: Sequence[Dict[str, Any]], headers: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Drop CSV columns that have no values across all rows.

    Args:
        rows: Data rows.
        headers: Candidate CSV headers.

    Returns:
        tuple[list[str], list[str]]: Kept headers and removed headers.
    """
    kept: List[str] = []
    removed: List[str] = []
    for header in headers:
        if any(not is_empty_cell(row.get(header)) for row in rows):
            kept.append(header)
        else:
            removed.append(header)
    return kept, removed


def is_empty_cell(value: Any) -> bool:
    """Determine whether a cell should be treated as empty.

    Args:
        value: Cell value.

    Returns:
        bool: True if the value is blank-like.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def build_csv_headers(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Build a deterministic CSV header ordering from row keys.

    Args:
        rows: Flat data rows.

    Returns:
        list[str]: Ordered CSV columns.
    """
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())

    ordered_headers = [column for column in PREFERRED_CSV_COLUMNS if column in all_keys]
    remaining = sorted(all_keys - set(ordered_headers))
    return ordered_headers + remaining


def write_rows_to_csv(
    rows: Sequence[Dict[str, Any]],
    csv_path: Path,
    logger: logging.Logger,
    drop_empty: bool = False,
) -> None:
    """Write usage rows to a CSV file.

    Args:
        rows: Flat rows from OCI Usage API.
        csv_path: Destination CSV file path.
        logger: Logger for status output.
        drop_empty: Whether to remove all-empty columns.
    """
    if not rows:
        logger.warning("No rows returned by OCI Usage API; writing header-only CSV.")
        headers = PREFERRED_CSV_COLUMNS
    else:
        headers = build_csv_headers(rows)
        if drop_empty:
            headers, removed_headers = drop_empty_columns(rows, headers)
            if removed_headers:
                logger.info("Dropped all-empty columns: %s", ", ".join(removed_headers))

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize_total_cost(rows: Sequence[Dict[str, Any]]) -> Decimal:
    """Calculate total computed cost from row data.

    Args:
        rows: Flat rows from OCI Usage API.

    Returns:
        Decimal: Sum of computed_amount values parseable as decimals.
    """
    total = Decimal("0")
    for row in rows:
        value = row.get("computed_amount")
        if value is None:
            continue
        try:
            total += Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
    return total


def main() -> int:
    """Run the OCI cost query workflow and write CSV output.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    logger = setup_logging(args.verbose)

    try:
        start, end = resolve_time_range(args, logger)
        client, tenancy_id = get_usage_client(args, logger)
        rows = fetch_cost_rows(client, tenancy_id, start, end, args, logger)
    except (RuntimeError, ValueError, ServiceError, RequestException) as exc:
        logger.error("%s", exc)
        return 1

    default_name = f"oci-cost-export-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    csv_path = Path(args.csv) if args.csv else Path(default_name)
    try:
        write_rows_to_csv(rows, csv_path, logger, drop_empty=args.drop_empty_columns)
    except OSError as exc:
        logger.error("Failed writing CSV '%s': %s", csv_path, exc)
        return 1

    total_cost = summarize_total_cost(rows)
    logger.info("Rows written: %d", len(rows))
    logger.info("Total computed_amount (approx): %s", total_cost)
    logger.info("CSV output: %s", csv_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
