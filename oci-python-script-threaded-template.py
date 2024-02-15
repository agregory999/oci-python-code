# OCI Python Script template
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides ....<basic documenation>.....

# Usage: python oci-python-xxx-yyy.py

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry

# OCI Clients and models (import as necessary)
from oci.database import DatabaseClient
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor

# Threaded function
def work_function(ocid: str):
    # ADB Example
    try:
        database = database_client.get_autonomous_database(
            autonomous_database_id=ocid
        ).data

        logger.info(f"DB Name: {database.display_name}")
        logger.debug(f"Full Details: {database}")
    except ServiceError as ex:
        logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
        logger.debug(f"Full Exception Detail: {ex}")


# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose  # Boolean
    profile = args.profile  # String
    use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
    region = args.region # Region to use with Instance Principal, if not default
    threads = args.threads

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    # PHASE 2 - Creation of OCI Client(s) 
    try:

    # Client creation
        if use_instance_principals:
            logger.info(f"Using Instance Principal Authentication")

            signer = InstancePrincipalsSecurityTokenSigner()
            config_ip = {}
            if region:
                config_ip={"region": region}
                logger.info(f"Changing region to {region}")

            # Example of client
            database_client = DatabaseClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config=config_ip, signer=signer)

        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            # Create the OCI Client to use
            database_client = DatabaseClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # Create any necessary Clients
    db_client = DatabaseClient(config)

    # PHASE 3 - Main Script Execution (threaded)

    # Get Resource List via Search
    atp_db = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query autonomousdatabase resources'
        ),
        limit=1000
    ).data

    # Build a list of OCIDs to operate on
    db_ocids = []
    for i,db_it in enumerate(atp_db.items, start=1):
        db_ocids.append(db_it.identifier)

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(work_function, db_ocids)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

