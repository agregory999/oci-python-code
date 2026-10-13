#!/usr/bin/env python3
"""OCI cost query script (non-CSV) with stdout JSON output.

Examples:
  python oci_cost_query.py
  python oci_cost_query.py --days-back 7 --granularity DAILY --group-by service
  python oci_cost_query.py --mtd --dimension-filter service=COMPUTE
  python oci_cost_query.py --mtd --dimension-filter resourceId=ocid1.instance.oc1..example
  python oci_cost_query.py --start 2026-05-01 --end 2026-06-01 \
    --tag-filter Operations.CostCenter=ENG --json-out may_costs.json
"""

from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI options.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Query OCI Usage API for cost data and print JSON to stdout. "
            "Optionally write JSON to a file with --json-out."
        )
    )
    parser.add_argument("-p", "--profile", default="DEFAULT", help="OCI profile name.")
    parser.add_argument("--instance-principal", action="store_true", help="Use instance principal auth.")
    parser.add_argument("--region", help="Optional region override when using --instance-principal.")
    parser.add_argument("--start", help="Start in UTC YYYY-MM-DD or ISO8601.")
    parser.add_argument("--end", help="End in UTC YYYY-MM-DD or ISO8601.")
    parser.add_argument("--days-back", type=int, default=DEFAULT_DAYS_BACK, help="Relative day range.")
    parser.add_argument("--mtd", action="store_true", help="Month-to-date in UTC.")
    parser.add_argument("-g", "--granularity", choices=["HOURLY", "DAILY", "MONTHLY"], default="DAILY")
    parser.add_argument("--aggregate-by-time", action="store_true", help="Aggregate full time range.")
    parser.add_argument("--group-by", action="append", help="Repeatable group-by field.")
    parser.add_argument("--dimension-filter", action="append", help="Repeatable key=value filter.")
    parser.add_argument("--tag-filter", action="append", help="Repeatable namespace.key=value filter.")
    parser.add_argument("--filter-operator", choices=["AND", "OR"], default="AND")
    parser.add_argument("--compartment-depth", type=int, default=6)
    parser.add_argument("--json-out", help="Optional JSON output file path.")
    parser.add_argument("--summary-only", action="store_true", help="Print summary JSON only.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def setup_logging(verbose: bool) -> logging.Logger:
    """Configure and return logger.

    Args:
        verbose: Whether to enable debug logging.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger(__name__)


def parse_utc_datetime(value: str) -> datetime:
    """Parse date/time string into UTC datetime.

    Args:
        value: Date string in YYYY-MM-DD or ISO8601.

    Returns:
        datetime: UTC datetime.

    Raises:
        ValueError: If parsing fails.
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
    """Normalize datetime precision for Usage API granularity.

    Args:
        value: UTC datetime.
        granularity: HOURLY, DAILY, or MONTHLY.

    Returns:
        datetime: Normalized UTC datetime.
    """
    if granularity in {"DAILY", "MONTHLY"}:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(minute=0, second=0, microsecond=0)


def resolve_time_range(args: argparse.Namespace, logger: logging.Logger) -> Tuple[datetime, datetime]:
    """Resolve query time range from CLI inputs.

    Args:
        args: Parsed CLI args.
        logger: Logger instance.

    Returns:
        tuple[datetime, datetime]: (start, end) UTC datetimes.

    Raises:
        ValueError: If arguments are invalid.
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
    """Parse dimension filters into OCI models.

    Args:
        dimension_filters: key=value expressions.

    Returns:
        list[Dimension]: Parsed dimensions.
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
    """Parse tag filters into OCI models.

    Args:
        tag_filters: namespace.key=value expressions.

    Returns:
        list[Tag]: Parsed tags.
    """
    if not tag_filters:
        return []

    tags: List[Tag] = []
    for expression in tag_filters:
        if "=" not in expression or "." not in expression.split("=", 1)[0]:
            raise ValueError(f"Invalid --tag-filter '{expression}'. Expected namespace.key=value.")
        key_expr, value = expression.split("=", 1)
        namespace, key = key_expr.split(".", 1)
        namespace = namespace.strip()
        key = key.strip()
        value = value.strip()
        if not namespace or not key or not value:
            raise ValueError(f"Invalid --tag-filter '{expression}'. Expected namespace.key=value.")
        tags.append(Tag(namespace=namespace, key=key, value=value))
    return tags


def build_filter(args: argparse.Namespace) -> Filter | None:
    """Build optional OCI Usage API filter.

    Args:
        args: Parsed CLI args.

    Returns:
        Filter | None: OCI filter model or None.
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
    """Create Usage API client and return tenancy OCID.

    Args:
        args: Parsed CLI args.
        logger: Logger instance.

    Returns:
        tuple[UsageapiClient, str]: Usage client and tenancy OCID.
    """
    if args.instance_principal:
        signer = InstancePrincipalsSecurityTokenSigner()
        client_config: Dict[str, str] = {}
        if args.region:
            client_config["region"] = args.region
        logger.info("Auth mode: Instance Principal")
        return (
            UsageapiClient(
                config=client_config,
                signer=signer,
                retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
                timeout=600,
            ),
            signer.tenancy_id,
        )

    config_data = oci.config.from_file(profile_name=args.profile)
    logger.info("Auth mode: config file profile '%s'", args.profile)
    return (
        UsageapiClient(
            config=config_data,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
            timeout=600,
        ),
        config_data["tenancy"],
    )


def normalize_field_value(key: str, value: Any) -> Any:
    """Normalize row field values for JSON output.

    Args:
        key: Field key.
        value: Field value.

    Returns:
        Any: Normalized value.
    """
    if key == "tags" and isinstance(value, list) and value and all(
        isinstance(item, dict) and all(item.get(field) is None for field in ("namespace", "key", "value"))
        for item in value
    ):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def fetch_cost_rows(
    client: UsageapiClient,
    tenancy_id: str,
    start: datetime,
    end: datetime,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    """Fetch paginated Usage API cost rows.

    Args:
        client: Usage API client.
        tenancy_id: Tenancy OCID.
        start: Start datetime.
        end: End datetime.
        args: Parsed CLI args.
        logger: Logger instance.

    Returns:
        list[dict[str, Any]]: Normalized rows.
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

    rows: List[Dict[str, Any]] = []
    page = None
    while True:
        response = client.request_summarized_usages(
            request_summarized_usages_details=request,
            page=page,
        )
        for item in response.data.items:
            record = {k: normalize_field_value(k, v) for k, v in to_dict(item).items()}
            if not record.get("time_usage_started"):
                record["time_usage_started"] = start.isoformat()
            if not record.get("time_usage_ended"):
                record["time_usage_ended"] = end.isoformat()
            rows.append(record)
        page = response.next_page
        if not page:
            break

    return rows


def summarize_total_cost(rows: Sequence[Dict[str, Any]]) -> Decimal:
    """Compute decimal sum of computed_amount values.

    Args:
        rows: Usage rows.

    Returns:
        Decimal: Summed computed amount.
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


def print_json(data: Any) -> None:
    """Print JSON payload to stdout.

    Args:
        data: JSON-serializable data.
    """
    print(json.dumps(data, indent=2, default=str))


def main() -> int:
    """Run cost query and print non-CSV output.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    logger = setup_logging(args.verbose)

    try:
        start, end = resolve_time_range(args, logger)
        client, tenancy_id = get_usage_client(args, logger)
        rows = fetch_cost_rows(client, tenancy_id, start, end, args, logger)
    except (RuntimeError, ValueError, ServiceError, RequestException, ClientError) as exc:
        logger.error("%s", exc)
        return 1

    summary = {
        "row_count": len(rows),
        "total_computed_amount": str(summarize_total_cost(rows)),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
    }

    if args.summary_only:
        payload: Dict[str, Any] = {"summary": summary}
    else:
        payload = {"summary": summary, "items": rows}

    if args.json_out:
        out_path = Path(args.json_out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            logger.info("JSON output: %s", out_path.resolve())
        except OSError as exc:
            logger.error("Failed writing JSON output '%s': %s", out_path, exc)
            return 1

    print_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
