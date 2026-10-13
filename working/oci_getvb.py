# OCI Python Script template
# Copyright (c) 2024, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides an example of using a resource search to build a list of OCIDs, then a threaded executor to "do something" to each
# item in the list.  The work_function is called for each OCID, and the results are shown within the as_completed block.  
# The results can include an exception, which is handled in the as_completed block.

# Usage: python oci-threaded-work-resource-search.py
# Valid switches
# -v/--verbose for verbose/debug
# -ip/--instanceprincipal for Instance Principal (only on OCI VM)
# -r/--region for alternate region
# -pr/--profile for using a non-DEFAULT named OCI Profile
# -t/--threads for how many concurrent threads to run.  Don't go above 8 or the API may throw errors

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry

# OCI Clients and models (import as necessary)
from oci.database import DatabaseClient
from oci.visual_builder import VbInstanceClient
from oci.visual_builder.models import UpdateVbInstanceDetails
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
from concurrent import futures

DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"

# Threaded function
def work_function(ocid: str):
    # ADB Example - allow exceptions to flow through
    vbi = vb_client.get_vb_instance(
        vb_instance_id=f"{ocid}"
    ).data

    logger.debug(f"VB Name: {vbi.display_name} Enabled: {vbi.is_visual_builder_enabled}")
    logger.debug(f"VB All: {vbi}")

    if not vbi.attachments and vbi.lifecycle_state == "ACTIVE":
        logger.info(">>Standalone - reset schedule")
        current_tags = vbi.defined_tags
        current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}
        vb_client.update_vb_instance(vb_instance_id=vbi.id,
                                     update_vb_instance_details=UpdateVbInstanceDetails(defined_tags = current_tags)
                                     )
        logger.info(f">>Reset Schedule tag for VB: {vbi.display_name}")
        
    return vbi

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

            # Example of client
            database_client = DatabaseClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            vb_client = VbInstanceClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config=config_ip, signer=signer)

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
            vb_client = VbInstanceClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # Create any necessary Clients
    db_client = DatabaseClient(config)

    # PHASE 3 - Main Script Execution (threaded)

    # 2 examples for getting a list for threading
    # 1) Resource Search, create list of OCIDs
    # Get Resource List via Search
    vbs = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query visualbuilderinstance resources'
        ),
        limit=100
    ).data

    # Build a list of OCIDs to operate on
    vb_ocids = []
    for i,db_it in enumerate(vbs.items, start=1):
        vb_ocids.append(db_it.identifier)

    # Thread Pool with execution based on incoming list of DB OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = [executor.submit(work_function, ocid) for ocid in vb_ocids]
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

        # These are thread Futures - as each iteration completes, the result(what was returned or thrown) is logged
        for future in futures.as_completed(results):
            try:
                vbi = future.result()
                # if vbi.display_name == "oic_vbcs_ag-oic-phx":
                # if vbi.attachments and len(vbi.attachments) > 0:
                logger.debug(f"Result: {vbi.display_name} / {vbi.attachments}")

            except ServiceError as ex:
                logger.error(f"ERROR: {ex.message}")
                logger.debug(f"ERROR DETAIL: {ex}")
    logger.info(f"Finished submitting all tasks for parallel execution")
