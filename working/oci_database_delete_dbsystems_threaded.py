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
from concurrent.futures import ThreadPoolExecutor, Future
from concurrent import futures
import circuitbreaker

global total
total = 0

# Callback
def finish(future: Future):
    logger.debug(f"Future: {future.result()}")
    
    global total
    total += future.result()
    pass

# Threaded function
def work_function_dbsystem(ocid: str):
    # ADB Example - allow exceptions 
    # try:
    database = database_client.get_db_system(
        db_system_id=f"{ocid}"
    ).data

    logger.info(f"DB System Name: {database.display_name}. Lifecycle: {database.lifecycle_state}")
    
    if database.lifecycle_state != database.LIFECYCLE_STATE_AVAILABLE:
        logger.info(f"Not deleting {ocid} due to lifecycle other than {database.LIFECYCLE_STATE_AVAILABLE}")
        return f"No action for {database.display_name} OCID {ocid}"

    # Delete it
    try:
        logger.info(f"Terminating: {database.display_name} / {ocid}")
        database_client.terminate_db_system(
            db_system_id=ocid
        )
        logger.info(f"Terminated: {database.display_name} / {ocid}")
    except ServiceError as ex:
        logger.error(f"Failed to terminate {database.display_name} / {ocid}.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
        logger.debug(f"Full Exception Detail: {ex}")
    
    return database.display_name

# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-r", "--region", help="Use Instance Principal with alt region")
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

            # Could use composite operations
            # disable_database_management_and_wait_for_state
        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)
            if region:
                config["region"] = region
                logger.info(f"Changing region to {region}")

            # Create the OCI Client to use
            database_client = DatabaseClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # PHASE 3 - Main Script Execution (threaded)

    # 2 examples for getting a list for threading
    # 1) Resource Search, create list of OCIDs
    # Get Resource List via Search
    base_dbs = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query dbsystem resources'
        ),
        limit=1000
    ).data

    # Build a list of OCIDs to operate on
    db_ocids = []
    for i,db_it in enumerate(base_dbs.items, start=1):
        db_ocids.append(db_it.identifier)

    # 2) Use pagination and list_call_get_all_results, then pass actual objects as work items
    # Get all compartments (we don't know the depth of any), tenancy level
    # Using the paging API
    # paginated_response = pagination.list_call_get_all_results(
    #     identity_client.list_compartments,
    #     tenancy_ocid,
    #     access_level="ACCESSIBLE",
    #     sort_order="ASC",
    #     compartment_id_in_subtree=True,
    #     lifecycle_state="ACTIVE",
    #     limit=1000)
    # comp_list.extend(paginated_response.data)

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = [executor.submit(work_function_dbsystem, ocid) for ocid in db_ocids]
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

    # Thread Pool with execution based on incoming list of Compartments
    # with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
    #     results = [executor.submit(work_function, c) for c in comp_list]
    #     logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

        # # Add callbacks to report
        # for future in results:
        #     # future.add_done_callback(print)
        #     future.add_done_callback(finish)
    

        for future in futures.as_completed(results):
            try:
                logger.info(f"Result: {future.result()}")
            except ServiceError as ex:
                logger.error(f"ERROR: {ex.message}")
            except circuitbreaker.CircuitBreakerError as ex:
                logger.error(f"CB ERROR: {ex}")

    logger.info(f"Finished submitting all for parallel execution for {len(db_ocids)} DB Systems")
