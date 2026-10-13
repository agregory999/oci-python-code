#!/usr/bin/env python3
"""List, select, and execute OCI saved cost reports with screen/file output options."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import oci
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, RequestException, ServiceError
from oci.usage_api import UsageapiClient
from oci.usage_api.models import RequestSummarizedUsagesDetails
from oci.util import to_dict

LOGGER = logging.getLogger(__name__)
TABLE_DEFAULT_COLUMNS = [
    "time_usage_started",
    "time_usage_ended",
    "service",
    "sku_name",
    "resource_id",
    "computed_amount",
    "currency",
    "unit",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "List OCI saved cost reports (saved queries), prompt for selection by default, "
            "execute selected report, and output results as table/json/csv."
        )
    )
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument("-pr", "--profile", help="OCI profile name (default: DEFAULT).")
    auth_group.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication.",
    )

    parser.add_argument("--region", help="Optional region override.")
    parser.add_argument(
        "--compartment-id",
        help="Compartment OCID used for listing saved queries (defaults to tenancy).",
    )
    parser.add_argument(
        "--select-index",
        type=int,
        help="1-based index of saved report to execute. If omitted, prompt is shown.",
    )
    parser.add_argument(
        "--start",
        help="Optional explicit start timestamp in UTC (YYYY-MM-DD or ISO8601).",
    )
    parser.add_argument(
        "--end",
        help="Optional explicit end timestamp in UTC (YYYY-MM-DD or ISO8601).",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Relative time window in days when --start/--end are not used.",
    )
    parser.add_argument("--mtd", action="store_true", help="Use month-to-date in UTC.")
    parser.add_argument(
        "--output-destination",
        choices=["screen", "file"],
        default="screen",
        help="Where to send result output.",
    )
    parser.add_argument(
        "--output-type",
        choices=["table", "json", "csv"],
        default="table",
        help="Output representation format.",
    )
    parser.add_argument(
        "--output-path",
        help="Output file path when --output-destination file is selected.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")

    args = parser.parse_args()
    if args.days_back < 1:
        parser.error("--days-back must be >= 1")
    if args.output_destination == "file" and not args.output_path:
        parser.error("--output-path is required when --output-destination file is selected")
    if bool(args.start) ^ bool(args.end):
        parser.error("--start and --end must be provided together")
    if args.mtd and args.start:
        parser.error("Use either --mtd or --start/--end")
    if args.select_index is not None and args.select_index < 1:
        parser.error("--select-index must be >= 1")
    return args


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether to enable debug logging.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def parse_utc_datetime(value: str) -> datetime:
    """Parse date/time string into UTC datetime.

    Args:
        value: Date string in YYYY-MM-DD or ISO8601.

    Returns:
        datetime: Timezone-aware UTC datetime.
    """
    if len(value) == 10:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_time_range(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Resolve report execution time range.

    Args:
        args: Parsed CLI args.

    Returns:
        tuple[datetime, datetime]: Start/end UTC datetimes.
    """
    now_utc = datetime.now(timezone.utc)
    if args.start and args.end:
        return parse_utc_datetime(args.start), parse_utc_datetime(args.end)
    if args.mtd:
        return now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now_utc
    return now_utc - timedelta(days=args.days_back), now_utc


def create_usage_client(args: argparse.Namespace) -> tuple[UsageapiClient, str, str]:
    """Create OCI Usage API client and return tenancy/compartment values.

    Args:
        args: Parsed CLI args.

    Returns:
        tuple[UsageapiClient, str, str]: (client, tenancy_ocid, list_compartment_ocid).
    """
    if args.instance_principal:
        signer = InstancePrincipalsSecurityTokenSigner()
        client_config: dict[str, str] = {}
        if args.region:
            client_config["region"] = args.region
        client = UsageapiClient(
            config=client_config,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )
        tenancy_ocid = signer.tenancy_id
        return client, tenancy_ocid, args.compartment_id or tenancy_ocid

    profile_name = args.profile or "DEFAULT"
    config_data = oci.config.from_file(profile_name=profile_name)
    if args.region:
        config_data["region"] = args.region
    tenancy_ocid = config_data["tenancy"]
    client = UsageapiClient(config_data, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
    return client, tenancy_ocid, args.compartment_id or tenancy_ocid


def list_saved_queries(client: UsageapiClient, list_compartment_id: str) -> list[Any]:
    """List saved Usage API queries.

    Args:
        client: Usage API client.
        list_compartment_id: Compartment ID for saved query listing.

    Returns:
        list[Any]: Saved query model objects.
    """
    response = client.list_queries(compartment_id=list_compartment_id)
    if not response.data or not response.data.items:
        return []
    return list(response.data.items)


def display_saved_queries(queries: list[Any]) -> None:
    """Print numbered saved query list.

    Args:
        queries: Saved query model objects.
    """
    print("\nSaved Cost Reports")
    print("==================")
    for index, query in enumerate(queries, start=1):
        query_dict = to_dict(query)
        display_name = (
            query_dict.get("query_definition", {}).get("display_name")
            or query_dict.get("display_name")
            or "Unnamed"
        )
        print(f"{index:>3}. {display_name}  ({query_dict.get('id', 'no-id')})")


def prompt_for_selection(queries: list[Any]) -> int:
    """Prompt user to choose one saved query index.

    Args:
        queries: Saved query list.

    Returns:
        int: Zero-based selected index.
    """
    max_choice = len(queries)
    while True:
        user_input = input(f"\nSelect report to execute [1-{max_choice}, 0 exit]: ").strip()
        if user_input == "0":
            raise KeyboardInterrupt("User exited selection prompt.")
        try:
            choice = int(user_input)
            if 1 <= choice <= max_choice:
                return choice - 1
        except ValueError:
            pass
        print("Invalid selection.")


def build_request_from_saved_query(
    selected_query: Any,
    tenancy_ocid: str,
    start_utc: datetime,
    end_utc: datetime,
) -> RequestSummarizedUsagesDetails:
    """Build execution request from saved query definition.

    Args:
        selected_query: Saved query model object.
        tenancy_ocid: Tenancy OCID.
        start_utc: Execution start time.
        end_utc: Execution end time.

    Returns:
        RequestSummarizedUsagesDetails: Executable request model.

    Raises:
        ValueError: If saved report definition is missing required shape.
    """
    query_dict = to_dict(selected_query)
    report_query = query_dict.get("query_definition", {}).get("report_query")
    if not isinstance(report_query, dict):
        raise ValueError("Selected saved query has no report_query definition.")

    request_kwargs: dict[str, Any] = {
        "tenant_id": tenancy_ocid,
        "time_usage_started": start_utc,
        "time_usage_ended": end_utc,
        "query_type": report_query.get("query_type") or RequestSummarizedUsagesDetails.QUERY_TYPE_COST,
        "compartment_depth": report_query.get("compartment_depth", 6.0),
        "is_aggregate_by_time": report_query.get("is_aggregate_by_time", False),
        "granularity": report_query.get("granularity", RequestSummarizedUsagesDetails.GRANULARITY_DAILY),
    }

    optional_keys = ["group_by", "group_by_tag", "filter", "forecast"]
    for key in optional_keys:
        if key in report_query and report_query[key] is not None:
            request_kwargs[key] = report_query[key]

    return RequestSummarizedUsagesDetails(**request_kwargs)


def execute_saved_query(
    client: UsageapiClient,
    request: RequestSummarizedUsagesDetails,
) -> list[dict[str, Any]]:
    """Execute saved query request and return flattened row dictionaries.

    Args:
        client: Usage API client.
        request: Prepared usage request.

    Returns:
        list[dict[str, Any]]: Normalized report rows.
    """
    rows: list[dict[str, Any]] = []
    page = None
    while True:
        response = client.request_summarized_usages(
            request_summarized_usages_details=request,
            page=page,
        )
        for item in response.data.items:
            rows.append(to_dict(item))
        page = response.next_page
        if not page:
            break
    return rows


def make_table(rows: list[dict[str, Any]]) -> str:
    """Render rows as a readable pipe-separated table.

    Args:
        rows: Data rows.

    Returns:
        str: Table-formatted text.
    """
    if not rows:
        return "No rows returned."

    all_keys = set().union(*(row.keys() for row in rows))
    ordered_columns = [column for column in TABLE_DEFAULT_COLUMNS if column in all_keys]
    ordered_columns.extend(sorted(all_keys - set(ordered_columns)))

    width_by_column: dict[str, int] = {}
    for column in ordered_columns:
        max_data_len = max(len(str(row.get(column, ""))) for row in rows)
        width_by_column[column] = min(max(len(column), max_data_len), 50)

    def format_row(row_data: dict[str, Any]) -> str:
        cells: list[str] = []
        for column in ordered_columns:
            text = str(row_data.get(column, ""))
            if len(text) > width_by_column[column]:
                text = text[: width_by_column[column] - 3] + "..."
            cells.append(text.ljust(width_by_column[column]))
        return "| " + " | ".join(cells) + " |"

    header = format_row({column: column for column in ordered_columns})
    separator = "|" + "|".join("-" * (width_by_column[column] + 2) for column in ordered_columns) + "|"
    body = "\n".join(format_row(row) for row in rows)
    return f"{header}\n{separator}\n{body}"


def make_csv(rows: list[dict[str, Any]]) -> str:
    """Render rows as CSV text.

    Args:
        rows: Data rows.

    Returns:
        str: CSV-formatted text.
    """
    if not rows:
        return ""

    headers = sorted(set().union(*(row.keys() for row in rows)))
    output_lines: list[str] = []
    output_lines.append(",".join(headers))
    for row in rows:
        values = []
        for header in headers:
            cell = row.get(header, "")
            cell_text = str(cell)
            if any(ch in cell_text for ch in [",", '"', "\n"]):
                cell_text = '"' + cell_text.replace('"', '""') + '"'
            values.append(cell_text)
        output_lines.append(",".join(values))
    return "\n".join(output_lines) + "\n"


def render_output(output_type: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    """Render output content in requested representation.

    Args:
        output_type: table, json, or csv.
        rows: Result rows.
        summary: Execution summary metadata.

    Returns:
        str: Rendered output content.
    """
    if output_type == "json":
        return json.dumps({"summary": summary, "items": rows}, indent=2, default=str)
    if output_type == "csv":
        return make_csv(rows)
    return make_table(rows)


def write_output(destination: str, output_path: str | None, content: str) -> None:
    """Write rendered output to screen or file.

    Args:
        destination: screen or file.
        output_path: Output path when destination=file.
        content: Rendered content.
    """
    if destination == "screen":
        print("\n" + content)
        return

    if not output_path:
        raise ValueError("output_path is required for file destination")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    LOGGER.info("Wrote output to %s", path.resolve())


def main() -> int:
    """Run saved report listing, selection, execution, and output flow.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)

    errors: list[str] = []

    try:
        client, tenancy_ocid, list_compartment = create_usage_client(args)
    except (ClientError, ValueError) as exc:
        LOGGER.critical("OCI client initialization failed: %s", exc)
        return 2

    try:
        queries = list_saved_queries(client, list_compartment)
    except (ServiceError, RequestException, Exception) as exc:  # pylint: disable=broad-except
        LOGGER.error("Failed to list saved queries: %s", exc)
        return 1

    if not queries:
        LOGGER.warning("No saved queries found in compartment %s", list_compartment)
        return 0

    display_saved_queries(queries)

    try:
        selected_index = args.select_index - 1 if args.select_index else prompt_for_selection(queries)
    except KeyboardInterrupt:
        LOGGER.info("Selection cancelled by user.")
        return 0

    if not (0 <= selected_index < len(queries)):
        LOGGER.error("Selected index %s is out of range.", args.select_index)
        return 1

    start_utc, end_utc = resolve_time_range(args)
    selected_query = queries[selected_index]
    selected_query_dict = to_dict(selected_query)
    report_name = (
        selected_query_dict.get("query_definition", {}).get("display_name")
        or selected_query_dict.get("display_name")
        or "Unnamed"
    )
    LOGGER.info("Executing saved report: %s", report_name)
    LOGGER.info("Execution time range UTC: %s to %s", start_utc.isoformat(), end_utc.isoformat())

    try:
        request = build_request_from_saved_query(selected_query, tenancy_ocid, start_utc, end_utc)
    except ValueError as exc:
        LOGGER.error("Unable to build execution request: %s", exc)
        return 1

    try:
        rows = execute_saved_query(client, request)
    except (ServiceError, RequestException, Exception) as exc:  # pylint: disable=broad-except
        error_text = f"Saved report execution failed: {exc}"
        LOGGER.error(error_text)
        errors.append(error_text)
        rows = []

    summary = {
        "report_name": report_name,
        "report_id": selected_query_dict.get("id"),
        "start_utc": start_utc.isoformat(),
        "end_utc": end_utc.isoformat(),
        "row_count": len(rows),
        "execution_errors": len(errors),
    }

    content = render_output(args.output_type, rows, summary)

    try:
        write_output(args.output_destination, args.output_path, content)
    except (OSError, ValueError) as exc:
        LOGGER.error("Failed writing output: %s", exc)
        return 1

    if errors:
        LOGGER.warning("Execution completed with %d errors.", len(errors))
        return 1

    LOGGER.info("Execution complete. Rows: %d", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
