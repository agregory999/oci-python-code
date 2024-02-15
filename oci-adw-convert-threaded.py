# ADW Convert ECPU and lower backup storage
# Runs in region with instance Principal
# Runs additional region with profile
# Added Multi-threading

# Written by Andrew Gregory
# 2/14/2024 v1

# Generic Imports
import argparse
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
import time
import datetime
import json

# OCI Imports
from oci import config
from oci import database
from oci import identity
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database.models import UpdateAutonomousDatabaseDetails
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails
from oci.exceptions import ServiceError

import oci

# Constants
DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"

# Helper function
def wait_for_available(db_id: str, start:bool):

    # Get updated
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
    ).data

    if start:
        if db.lifecycle_state == "STOPPED":
            # Start first
            logger.info(f'{"DRYRUN: " if dryrun else ""}Starting Autonomous DB: {db.display_name}')
            if dryrun:
                return
            database_client.start_autonomous_database(db.id)

    if dryrun:
        logger.debug("Not waiting for AVAILABLE")
        return
    # Waiting for AVAILABLE
    get_db_response = database_client.get_autonomous_database(db.id)
    oci.wait_until(database_client, get_db_response, 'lifecycle_state', 'AVAILABLE')

    logger.debug(f"Autonomous DB: {db.display_name} AVAILABLE")

# Helper function
def return_to_initial(db_id: str, initial:str):

    # Get updated
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
    ).data

    # Stop the DB if it was already stopped
    if initial == "STOPPED" and db.lifecycle_state == "AVAILABLE":
        logger.info(f'{"DRYRUN: " if dryrun else ""}Stopping Autonomous DB: {db.display_name}')
        if dryrun:
            return
        database_client.stop_autonomous_database(db.id)

    logger.debug(f"Kicked off STOP Autonomous for DB: {db.display_name} (Not Waiting)")

# Threaded function
def database_work(db_id: str):

    # Sleep a sec
    time.sleep(0.5)
    
    # Get reference
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
        ).data

    # Get Initial Lifecycle to return to afterwards
    db_initial_lifecycle_state = db.lifecycle_state

    # Return Val
    did_work = {}
    did_work["Detail"] = {"Name": f"{db.display_name}", "OCID": f"{db.id}", "Original CPU": f"{db.compute_model}", "License": f"{db.license_model}"}

    # Now try it
    try:
        # Show before
        logger.info(f"----{db_id}----Examine ({db.display_name})----------")
        logger.info(f'CPU Model: {db.compute_model} Dedicated: {db.is_dedicated} DG Role: {db.role}')
        logger.info(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs}")
        logger.info(f"License Model: {db.license_model} Edition: {db.database_edition} ")
        logger.info(f"----{db_id}----Start ({db.display_name})----------")

        if db.is_dedicated:
            logger.debug("Don't operate on dedicated")
            did_work["No-op"] = {"Dedicated": True}
            return did_work

        if db.lifecycle_state == "STANDBY" or db.role == "BACKUP_COPY":
            logger.debug("Don't operate on anything but primary")
            did_work["No-op"] = {"Role": f"{db.role}"}
            return did_work

        if db.is_free_tier:
            logger.debug("Don't operate on free ATP")
            did_work["No-op"] = {"Free": f"{db.is_free_tier}"}
            return did_work

        if db.lifecycle_state == "UNAVAILABLE":
            logger.debug("Don't operate on UNAVAILABLE DBs")
            did_work["No-op"] = {"Lifecycle": f"{db.lifecycle_state}"}

            return did_work

        # Compute Model - to ECPU
        logger.debug(f'CPU Model: {db.compute_model} Count: {db.compute_count if db.compute_model == "OCPU" else db.compute_count}')
        if db.compute_model == "OCPU":

            # Actual Conversion
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Converting ECPU Autonomous DB: {db.display_name}')

            wait_for_available(db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        backup_retention_period_in_days=backup_retention,
                        compute_model="ECPU"
                        )
                )
            # Waiting for AVAILABLE
            wait_for_available(db_id=db.id, start=False)

            did_work["ECPU"] = {"convert": True}

            logger.info(f'{"DRYRUN: " if dryrun else ""}Converted ECPU Autonomous DB: {db.display_name}')

        # Update backup Retention to save on cost
        if db.backup_retention_period_in_days > backup_retention:
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Update Backup retention DB: {db.display_name} to configured {backup_retention} days')
            wait_for_available(db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        backup_retention_period_in_days=backup_retention
                    )
                )

            did_work["Backups"] = {"Retention": backup_retention}

            # Waiting for AVAILABLE
            wait_for_available(db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Updated License DB: {db.display_name} to BYOL / SE')


        # License Model - BYOL and SE
        if db.license_model == "LICENSE_INCLUDED":
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Update License DB: {db.display_name} to BYOL / SE')

            wait_for_available(db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        license_model="BRING_YOUR_OWN_LICENSE",
                        database_edition="STANDARD_EDITION"
                    )
                )

            did_work["License"] = {"BYOL": True, "SE": True}

            # Waiting for AVAILABLE
            wait_for_available(db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Updated License DB: {db.display_name} to BYOL / SE')

        # Tagging - require Schedule Tag

        current_tags = db.defined_tags
        if "Schedule" in current_tags:
            logger.debug(f'Current Schedule: {current_tags["Schedule"]}')
            # Check tag for all 1
            schedule_tag = current_tags["Schedule"]
            if 'AnyDay' in schedule_tag:
                logger.debug(f'AnyDay tag: {schedule_tag["AnyDay"]}')
                if "0" in schedule_tag["AnyDay"]:
                    logger.debug("Compliant - will stop")
                else:
                    logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Not compliant({schedule_tag["AnyDay"]}) - will not stop - fixing')
                    current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}

                    # Start and wait if needed
                    wait_for_available(db_id=db.id, start=True)

                    if not dryrun:
                        database_client.update_autonomous_database(
                            autonomous_database_id=db.id,
                            update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                                defined_tags=current_tags
                            )
                        )
                    wait_for_available(db_id=db.id, start=False)
                    did_work["Tag"] = {"default": True}

        else:
            # Add default tag to defined tags
            current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}

            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Updating Tags DB: {db.display_name} to Schedule / AnyDay Default')

            # Start and wait if needed
            wait_for_available(db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        defined_tags=current_tags
                    )
                )
            did_work["Tag"] = {"default": True}

            wait_for_available(db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Updated Tags DB: {db.display_name} to Schedule / AnyDay Default')
        
        # Return to initial state
        return_to_initial(db_id=db.id,initial=db_initial_lifecycle_state)

        logger.info(f"----{db_id}----Complete ({db.display_name})----------")
    except ServiceError as exc:
        logger.error(f"Failed to complete action for DB: {db.display_name} \nReason: {exc}")
        did_work["Error"] = {"Exception": exc.message}
    
    return did_work    
    # End main function

# Only if called in Main
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("--dryrun", help="Dry Run - no action", action="store_true")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)
    parser.add_argument("-r", "--retention", help="Days of backup retention (def=14)", type=int, default=14)

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal
    region = args.region
    dryrun = args.dryrun
    threads = args.threads
    backup_retention = args.retention

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger('oci-scale-atp')
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    # Client creation
    if use_instance_principals:
        logger.info(f"Using Instance Principal Authentication")

        signer = InstancePrincipalsSecurityTokenSigner()
        config_ip = {}
        if region:
            config_ip={"region": region}
            logger.info(f"Changing region to {region}")
        database_client = database.DatabaseClient(config=config_ip, signer=signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        search_client = ResourceSearchClient(config=config_ip, signer=signer)

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        database_client = database.DatabaseClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        search_client = ResourceSearchClient(config)

    # Main routine
    # Grab all ADW serverless
    # Loop through
    # Ensure:
    # 1) Updated to ECPU
    # 2) License is BYOL / Standard
    # 3) Storage is scaled down
    # 4) Tags for AnyDay are there and not 1,1,1


    # Get ATP (Search)
    atp_db = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query autonomousdatabase resources return allAdditionalFields where (workloadType="ADW")'
        ),
        limit=1000
    ).data

    # Build a list of IDs
    db_ocids = []
    for i,db_it in enumerate(atp_db.items, start=1):
        db_ocids.append(db_it.identifier)

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(database_work, db_ocids)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")
    
    # Write to file
    datestring = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    filename = f'oci-adw-convert-ecpu-{datestring}.json'
    with open(filename,"w") as outfile:

        for result in results:
            logger.info(f"Result: {result}")
            outfile.write(json.dumps(result, indent=2))

    logging.info(f"Script complete - wrote JSON to {filename}.")