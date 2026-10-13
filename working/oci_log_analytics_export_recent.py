#!/usr/bin/env python3
"""Export OCI Log Analytics query results using a relative time window (hours or days)."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

from oci import config as oci_config
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, ServiceError
from oci.log_analytics import LogAnalyticsClient
from oci.log_analytics.models import ExportDetails, TimeRange

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Export OCI Log Analytics data for the last N hours or days."
    )

    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument("-pr", "--profile", help="OCI profile (defaults to DEFAULT).")
    auth_group.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication.",
    )

    window_group = parser.add_mutually_exclusive_group(required=True)
    window_group.add_argument("--hours", type=int, help="Relative lookback window in hours.")
    window_group.add_argument("--days", type=int, help="Relative lookback window in days.")

    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("-q", "--query", help="Log Analytics query string.")
    query_group.add_argument("--query-file", help="Path to text file with query.")

    parser.add_argument("-ns", "--namespace", required=True, help="Log Analytics namespace.")
    parser.add_argument("-c", "--compartment-ocid", required=True, help="Compartment OCID.")
    parser.add_argument("-r", "--region", help="Region override.")
    parser.add_argument("-tz", "--timezone", default="UTC", help="Timezone string (default: UTC).")
    parser.add_argument("-m", "--max-records", type=int, default=1_000_000, help="Max records.")
    parser.add_argument(
        "-f",
        "--format",
        default="CSV",
        choices=["CSV", "JSON"],
        help="Output format (default: CSV).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="log_analytics_recent_export.csv",
        help="Output file path.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logs.")

    args = parser.parse_args()
    if args.hours is not None and args.hours < 1:
        parser.error("--hours must be >= 1")
    if args.days is not None and args.days < 1:
        parser.error("--days must be >= 1")
    if args.max_records < 1:
        parser.error("--max-records must be >= 1")
    return args


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether to enable debug logging.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_query(args: argparse.Namespace) -> str:
    """Load query text from direct argument or file.

    Args:
        args: Parsed CLI arguments.

    Returns:
        str: Query text.

    Raises:
        ValueError: If the query is empty.
        OSError: If the file cannot be read.
    """
    if args.query_file:
        query_text = Path(args.query_file).read_text(encoding="utf-8").strip()
    else:
        query_text = (args.query or "").strip()

    if not query_text:
        raise ValueError("Query cannot be empty.")
    return query_text


def create_client(args: argparse.Namespace) -> LogAnalyticsClient:
    """Create OCI Log Analytics client.

    Args:
        args: Parsed CLI arguments.

    Returns:
        LogAnalyticsClient: Initialized client.

    Raises:
        ClientError: If OCI client creation fails.
    """
    if args.instance_principal:
        signer = InstancePrincipalsSecurityTokenSigner()
        config_data: dict[str, Any] = {}
        if args.region:
            config_data["region"] = args.region
        return LogAnalyticsClient(
            config=config_data,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )

    profile_name = args.profile or "DEFAULT"
    config_data = oci_config.from_file(profile_name=profile_name)
    if args.region:
        config_data["region"] = args.region

    return LogAnalyticsClient(config_data, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)


def calculate_window(args: argparse.Namespace) -> tuple[datetime.datetime, datetime.datetime]:
    """Calculate relative export start and end times.

    Args:
        args: Parsed CLI arguments.

    Returns:
        tuple[datetime.datetime, datetime.datetime]: (start_time, end_time) in UTC.
    """
    end_time = datetime.datetime.now(datetime.timezone.utc)
    if args.hours is not None:
        delta = datetime.timedelta(hours=args.hours)
    else:
        delta = datetime.timedelta(days=args.days)
    return end_time - delta, end_time


def run_export(args: argparse.Namespace) -> int:
    """Run relative-window log export.

    Args:
        args: Parsed CLI arguments.

    Returns:
        int: Exit code.
    """
    try:
        query_text = load_query(args)
    except (OSError, ValueError) as exc:
        LOGGER.error("Input validation failed: %s", exc)
        return 2

    try:
        client = create_client(args)
    except (ClientError, ValueError) as exc:
        LOGGER.critical("OCI client initialization failed: %s", exc)
        return 2

    start_time, end_time = calculate_window(args)
    export_details = ExportDetails(
        compartment_id=args.compartment_ocid,
        sub_system="LOG",
        query_string=query_text,
        output_format=args.format,
        time_filter=TimeRange(
            time_start=start_time,
            time_end=end_time,
            time_zone=args.timezone,
        ),
        max_total_count=args.max_records,
        should_include_columns=True,
    )

    output_path = Path(args.output)
    errors: list[str] = []

    try:
        response = client.export_query_result(
            namespace_name=args.namespace,
            export_details=export_details,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.data.content)  # type: ignore[arg-type]
        LOGGER.info(
            "Export complete: start=%s end=%s file=%s size=%d",
            start_time,
            end_time,
            output_path,
            output_path.stat().st_size,
        )
    except ServiceError as exc:
        error_message = (
            f"service={exc.target_service} op={exc.operation_name} "
            f"status={exc.status} code={exc.code} message={exc.message}"
        )
        LOGGER.error(error_message)
        errors.append(error_message)
    except Exception as exc:  # pylint: disable=broad-except
        error_message = f"unexpected_error message={exc}"
        LOGGER.error(error_message)
        errors.append(error_message)

    if errors:
        LOGGER.warning("Export finished with %d errors.", len(errors))
        return 1
    return 0


def main() -> int:
    """Script entrypoint.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)
    return run_export(args)


if __name__ == "__main__":
    sys.exit(main())
