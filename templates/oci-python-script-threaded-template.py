#!/usr/bin/env python3
"""Self-contained threaded OCI template with optional callback mode and aggregated error handling."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from concurrent import futures
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from oci import config as oci_config
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database import DatabaseClient
from oci.exceptions import ClientError, ServiceError
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails

LOGGER = logging.getLogger(__name__)


@dataclass
class CallbackStats:
    """Thread-safe callback state for threaded executions.

    Attributes:
        success_count: Number of successful callback completions.
        error_messages: Collected callback error messages.
        lock: Synchronization lock for shared counters/lists.
    """

    success_count: int = 0
    error_messages: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_success(self) -> None:
        """Record a successful callback completion."""
        with self.lock:
            self.success_count += 1

    def record_error(self, error_message: str) -> None:
        """Record an error message from callback processing.

        Args:
            error_message: Error detail to store.
        """
        with self.lock:
            self.error_messages.append(error_message)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Threaded OCI template. "
            "Uses Resource Search to discover resources, then processes each item in a thread pool."
        )
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument("-r", "--region", help="Optional region override.")
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=5,
        help="Thread pool size (default: 5).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=100,
        help="Maximum resource items to process (default: 100).",
    )

    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "-pr",
        "--profile",
        help="OCI config profile to use (defaults to DEFAULT when omitted).",
    )
    auth_group.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication.",
    )

    result_group = parser.add_mutually_exclusive_group()
    result_group.add_argument(
        "--use-callback",
        action="store_true",
        help="Use add_done_callback pattern for per-future completion handling.",
    )
    result_group.add_argument(
        "--use-as-completed",
        action="store_true",
        help="Use as_completed pattern for result handling (default).",
    )

    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be >= 1")
    if args.max_items < 1:
        parser.error("--max-items must be >= 1")
    return args


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether DEBUG-level logs should be enabled.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s",
    )


def create_clients(args: argparse.Namespace) -> tuple[DatabaseClient, ResourceSearchClient]:
    """Create required OCI clients for threaded processing.

    Args:
        args: Parsed command-line arguments.

    Returns:
        tuple[DatabaseClient, ResourceSearchClient]: Initialized clients.

    Raises:
        ClientError: If client initialization fails.
    """
    if args.instance_principal:
        LOGGER.info("Using instance principal authentication.")
        signer = InstancePrincipalsSecurityTokenSigner()
        config_data: dict[str, Any] = {}
        if args.region:
            config_data["region"] = args.region
        return (
            DatabaseClient(
                config=config_data,
                signer=signer,
                retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
            ),
            ResourceSearchClient(config=config_data, signer=signer),
        )

    profile_name = args.profile or "DEFAULT"
    LOGGER.info("Using OCI config profile: %s", profile_name)
    config_data = oci_config.from_file(profile_name=profile_name)
    if args.region:
        config_data["region"] = args.region

    return (
        DatabaseClient(config_data, retry_strategy=retry.DEFAULT_RETRY_STRATEGY),
        ResourceSearchClient(config_data),
    )


def discover_autonomous_database_ids(
    search_client: ResourceSearchClient,
    max_items: int,
) -> list[str]:
    """Discover autonomous database OCIDs using OCI Resource Search.

    Args:
        search_client: OCI resource search client.
        max_items: Maximum IDs to return.

    Returns:
        list[str]: Autonomous database OCIDs.
    """
    response = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type="Structured",
            query="query autonomousdatabase resources",
        ),
        limit=max_items,
    ).data

    autonomous_database_ids = [item.identifier for item in response.items if item.identifier]
    LOGGER.info("Discovered %d autonomous database IDs.", len(autonomous_database_ids))
    return autonomous_database_ids


def process_one_autonomous_database(database_client: DatabaseClient, autonomous_database_id: str) -> str:
    """Fetch and summarize one autonomous database.

    Args:
        database_client: OCI database client.
        autonomous_database_id: Autonomous database OCID.

    Returns:
        str: Short success summary.

    Raises:
        ServiceError: If the OCI request fails.
    """
    database = database_client.get_autonomous_database(
        autonomous_database_id=autonomous_database_id,
    ).data
    return f"ADB={database.display_name} OCID={autonomous_database_id} STATE={database.lifecycle_state}"


def callback_handler(
    future: Future,
    adb_id: str,
    stats: CallbackStats,
) -> None:
    """Handle one completed future when callback mode is enabled.

    Args:
        future: Completed future object.
        adb_id: Resource OCID associated with this future.
        stats: Shared callback state.
    """
    try:
        LOGGER.info("%s", future.result())
        stats.record_success()
    except ServiceError as exc:
        error_message = (
            f"adb_id={adb_id} service={exc.target_service} op={exc.operation_name} "
            f"status={exc.status} code={exc.code} message={exc.message}"
        )
        LOGGER.error(error_message)
        stats.record_error(error_message)
    except Exception as exc:  # pylint: disable=broad-except
        error_message = f"adb_id={adb_id} unexpected_error message={exc}"
        LOGGER.error(error_message)
        stats.record_error(error_message)


def run_with_callback_mode(
    database_client: DatabaseClient,
    autonomous_database_ids: list[str],
    threads: int,
) -> tuple[int, list[str]]:
    """Run threaded processing using add_done_callback.

    Args:
        database_client: OCI database client.
        autonomous_database_ids: Work-item OCIDs.
        threads: Maximum thread count.

    Returns:
        tuple[int, list[str]]: (success count, error messages).
    """
    stats = CallbackStats()
    with ThreadPoolExecutor(max_workers=threads, thread_name_prefix="worker") as executor:
        submitted_futures: list[Future] = []
        for adb_id in autonomous_database_ids:
            future = executor.submit(process_one_autonomous_database, database_client, adb_id)
            future.add_done_callback(lambda f, item_id=adb_id: callback_handler(f, item_id, stats))
            submitted_futures.append(future)

        futures.wait(submitted_futures)

    return stats.success_count, stats.error_messages


def run_with_as_completed_mode(
    database_client: DatabaseClient,
    autonomous_database_ids: list[str],
    threads: int,
) -> tuple[int, list[str]]:
    """Run threaded processing using as_completed.

    Args:
        database_client: OCI database client.
        autonomous_database_ids: Work-item OCIDs.
        threads: Maximum thread count.

    Returns:
        tuple[int, list[str]]: (success count, error messages).
    """
    success_count = 0
    error_messages: list[str] = []

    with ThreadPoolExecutor(max_workers=threads, thread_name_prefix="worker") as executor:
        future_to_id = {
            executor.submit(process_one_autonomous_database, database_client, adb_id): adb_id
            for adb_id in autonomous_database_ids
        }

        for future in futures.as_completed(future_to_id):
            adb_id = future_to_id[future]
            try:
                LOGGER.info("%s", future.result())
                success_count += 1
            except ServiceError as exc:
                error_message = (
                    f"adb_id={adb_id} service={exc.target_service} op={exc.operation_name} "
                    f"status={exc.status} code={exc.code} message={exc.message}"
                )
                LOGGER.error(error_message)
                error_messages.append(error_message)
            except Exception as exc:  # pylint: disable=broad-except
                error_message = f"adb_id={adb_id} unexpected_error message={exc}"
                LOGGER.error(error_message)
                error_messages.append(error_message)

    return success_count, error_messages


def main() -> int:
    """Execute threaded template workflow.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)

    try:
        database_client, search_client = create_clients(args)
    except (ClientError, ValueError) as exc:
        LOGGER.critical("Client initialization failed: %s", exc)
        return 2

    try:
        autonomous_database_ids = discover_autonomous_database_ids(search_client, args.max_items)
    except ServiceError as exc:
        LOGGER.critical(
            "Resource discovery failed: service=%s op=%s status=%s code=%s message=%s",
            exc.target_service,
            exc.operation_name,
            exc.status,
            exc.code,
            exc.message,
        )
        return 2

    if not autonomous_database_ids:
        LOGGER.info("No autonomous databases to process.")
        return 0

    if args.use_callback:
        success_count, error_messages = run_with_callback_mode(
            database_client,
            autonomous_database_ids,
            args.threads,
        )
    else:
        success_count, error_messages = run_with_as_completed_mode(
            database_client,
            autonomous_database_ids,
            args.threads,
        )

    LOGGER.info(
        "Threaded execution complete: successes=%d failures=%d",
        success_count,
        len(error_messages),
    )
    return 1 if error_messages else 0


if __name__ == "__main__":
    sys.exit(main())
