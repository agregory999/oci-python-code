# OCI Python Script template
# Copyright (c) 2024, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides an example of paginated get-all API call.  For example, all Compartments in tenancy.
# Once each required operation is added to the ThreadPoolExecutor, the as_completed block shows the results of each thread as it finishes the work.
# Exceptions or returned objects can be part of the returned Future (called result)

# Usage: python oci-threaded-work-list-get-all.py
# Valid switches
# -v/--verbose for verbose/debug
# -ip/--instanceprincipal for Instance Principal (only on OCI VM)
# -r/--region for alternate region
# -pr/--profile for using a non-DEFAULT named OCI Profile
# -t/--threads for how many concurrent threads to run.  Don't go above 8 or the API may throw errors

# Only import required code from OCI
from oci import config
from oci import pagination
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry

# OCI Clients and models (import as necessary)
from oci.identity import IdentityClient
from oci.identity.models import Compartment
from oci.stack_monitoring import StackMonitoringClient

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor, Future
from concurrent import futures

# Threaded function
def work_function(comp: Compartment):
    # Compartment Example - allow exceptions 

    logger.debug(f"Compartment Name: {comp.name}")
    logger.debug(f"Full Details: {comp}")

    res = stackmon_client.list_monitored_resources(
        compartment_id=comp.id
    ).data
    total = 0
    for r in res.items:
        logger.info(f"Comp: {comp.name} | Res Name: {r.name} / {r.id}")
        stackmon_client.delete_monitored_resource(
            monitored_resource_id=r.id,
            is_delete_members=True
        )
        total += 1
        logger.info(f"Deleted Res Name: {r.name} / {r.id}")


    return f"Comp: {comp.name} | total: {total}"

# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-r", "--region", help="Use alternate region")
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
            tenancy_ocid = signer.tenancy_id
            # Example of client
            identity_client = IdentityClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            stackmon_client = StackMonitoringClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)
            if region:
                config["region"] = region
                logger.info(f"Changing region to {region}")
            tenancy_ocid = config["tenancy"]
            # Create the OCI Client to use
            identity_client = IdentityClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            stackmon_client = StackMonitoringClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # PHASE 3 - Main Script Execution (threaded)

    # 2) Use pagination and list_call_get_all_results, then pass actual objects as work items
    # Get all compartments (we don't know the depth of any), tenancy level
    # Using the paging API
    comp_list = []
    paginated_response = pagination.list_call_get_all_results(
        identity_client.list_compartments,
        tenancy_ocid,
        access_level="ACCESSIBLE",
        sort_order="ASC",
        compartment_id_in_subtree=True,
        lifecycle_state="ACTIVE",
        limit=1000)
    comp_list.extend(paginated_response.data)

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = [executor.submit(work_function, comp) for comp in comp_list]
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

        for future in futures.as_completed(results):
            try:
                logger.info(f"Result: {future.result()}")
            except ServiceError as ex:
                logger.error(f"ERROR: {ex.message}")
    logger.info(f"Finished submitting all for parallel execution")
