# OCI Python Script template
# Copyright (c) 2026, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script uses OCI Resource Search to find Object Storage buckets in the tenancy,
# then uses a threaded function to log a bucket listing.
#
# Usage:
#   python oci-list-buckets-resource-search-threaded.py
#   python oci-list-buckets-resource-search-threaded.py -pr MYPROFILE -r us-ashburn-1 -t 8

# Only import required code from OCI
from oci import config as oci_config
from oci import pagination
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, ServiceError

# OCI Clients and models
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails

# Additional imports
import argparse
import logging
import re
import threading
import warnings
from collections import Counter
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger(__name__)


def get_additional_detail(resource, detail_name):
    """Return a Resource Search additional detail value when present."""
    if not resource.additional_details:
        return None

    return resource.additional_details.get(detail_name)


def get_bucket_region(resource):
    """Return the best available bucket region from Resource Search metadata."""
    for detail_name in ("region", "regionName", "region_name", "location"):
        detail_value = get_additional_detail(resource, detail_name)
        if detail_value:
            return detail_value

    for value in (resource.identifier, get_additional_detail(resource, "url")):
        if not value:
            continue

        match = re.search(r"objectstorage\.([a-z0-9-]+)\.oraclecloud\.com", value)
        if match:
            return match.group(1)

    return "unknown"


def work_function(bucket_resource):
    """Threaded worker that logs one bucket resource summary."""
    thread_name = threading.current_thread().name
    namespace = get_additional_detail(bucket_resource, "namespace")
    region = get_bucket_region(bucket_resource)

    logger.info(
        "Thread=%s Bucket=%s ResourceType=%s State=%s Region=%s Namespace=%s Compartment=%s Identifier=%s",
        thread_name,
        bucket_resource.display_name,
        bucket_resource.resource_type,
        bucket_resource.lifecycle_state,
        region,
        namespace if namespace else "unknown",
        bucket_resource.compartment_id,
        bucket_resource.identifier,
    )

    return {
        "bucket_name": bucket_resource.display_name,
        "region": region,
        "state": bucket_resource.lifecycle_state if bucket_resource.lifecycle_state else "unknown",
        "thread_name": thread_name,
    }


def log_summary(worker_results, failed_count):
    """Log a summary after all threaded bucket listing work is complete."""
    region_counts = Counter(result["region"] for result in worker_results)
    state_counts = Counter(result["state"] for result in worker_results)
    thread_counts = Counter(result["thread_name"] for result in worker_results)

    logger.info("Summary: completed=%s failed=%s total=%s", len(worker_results), failed_count, len(worker_results) + failed_count)
    logger.info("Summary by region: %s", dict(sorted(region_counts.items())))
    logger.info("Summary by state: %s", dict(sorted(state_counts.items())))
    logger.debug("Summary by worker thread: %s", dict(sorted(thread_counts.items())))


def create_search_client(profile, use_instance_principals, region):
    """Create an OCI Resource Search client from profile or instance principals."""
    if use_instance_principals:
        logger.info("Using Instance Principal Authentication")

        signer = InstancePrincipalsSecurityTokenSigner()
        config_ip = {}
        if region:
            config_ip = {"region": region}
            logger.info("Changing region to %s", region)

        return ResourceSearchClient(
            config=config_ip,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )

    logger.info("Using Profile Authentication: %s", profile)
    config = oci_config.from_file(profile_name=profile)
    if region:
        config["region"] = region
        logger.info("Changing region to %s", region)

    return ResourceSearchClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)


def search_bucket_resources(search_client, query):
    """Search all visible buckets in the tenancy."""
    logger.info("Running Resource Search query: %s", query)
    response = pagination.list_call_get_all_results(
        search_client.search_resources,
        search_details=StructuredSearchDetails(query=query),
        limit=1000,
    )

    if isinstance(response.data, list):
        return response.data

    return response.data.items


if __name__ == "__main__":
    warnings.filterwarnings(
        "ignore",
        message="The 'strict' parameter is no longer needed on Python 3+.*",
        category=FutureWarning,
        module="urllib3.poolmanager",
    )

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser(
        description="List Object Storage buckets found by OCI Resource Search using threaded workers."
    )
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-r", "--region", help="Use alternate region")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)
    parser.add_argument(
        "-q",
        "--query",
        help="Resource Search query to run",
        default="query bucket resources",
    )

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal
    region = args.region
    threads = args.threads
    query = args.query

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s")
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info('Using profile %s with Logging level %s', profile, "DEBUG" if verbose else "INFO")

    # PHASE 2 - Creation of OCI Client(s)
    try:
        search_client = create_search_client(profile, use_instance_principals, region)
    except ClientError as ex:
        logger.critical("Failed to connect to OCI: %s", ex)
        raise

    # PHASE 3 - Main Script Execution (threaded)
    try:
        bucket_resources = search_bucket_resources(search_client, query)
        logger.info("Found %s bucket resources", len(bucket_resources))

        with ThreadPoolExecutor(max_workers=threads, thread_name_prefix="bucket-worker") as executor:
            results = [executor.submit(work_function, bucket_resource) for bucket_resource in bucket_resources]
            logger.info("Kicked off %s threads for bucket listing", threads)

            worker_results = []
            failed_count = 0
            for future in futures.as_completed(results):
                try:
                    worker_result = future.result()
                    worker_results.append(worker_result)
                    logger.debug("Completed bucket listing for %s", worker_result["bucket_name"])
                except ServiceError as ex:
                    failed_count += 1
                    logger.error("OCI service error: %s", ex.message)
                    logger.debug("OCI service error detail: %s", ex)
                except Exception as ex:
                    failed_count += 1
                    logger.error("Thread failed: %s", ex)
                    logger.debug("Thread failure detail", exc_info=True)

        log_summary(worker_results, failed_count)

    except ServiceError as ex:
        logger.error(
            "Failed to call OCI. Target Service/Operation: %s/%s Code: %s Message: %s",
            ex.target_service,
            ex.operation_name,
            ex.code,
            ex.message,
        )
        logger.debug("Full Exception Detail: %s", ex)
        raise

    logger.info("Finished bucket listing")
