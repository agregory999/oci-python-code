# ATP/ADW Scale down script
# Runs in region with instance Principal
# Runs additional region with profile
# Added Multi-threading

# Written by Andrew Gregory
# 2/14/2024 v1
# 11/6/2024 v2 (combined ADW/ATP)

# Generic Imports
import argparse
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
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
from oci.resource_search.models import StructuredSearchDetails, ResourceSummary
from oci.exceptions import ServiceError
from oci.exceptions import ConfigFileNotFound

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
        logger.info(f"----{db.db_workload} / {db.display_name}----------")
        logger.debug(f"OCID: {db_id}")
        logger.info(f'CPU Model: {db.compute_model} Dedicated: {db.is_dedicated} DG Role: {db.role} Free: {db.is_free_tier} Dev: {db.is_dev_tier}')
        logger.info(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs}")
        logger.info(f"License Model: {db.license_model} Edition: {db.database_edition} ")
        logger.debug(f"----{db_id}----Start ({db.display_name})----------")

        if db.is_dedicated:
            logger.debug("Don't operate on dedicated")
            did_work["No-op"] = {"Dedicated": True}
            return did_work

        if db.role == "STANDBY":
            logger.debug("Don't operate on anything but primary")
            did_work["No-op"] = {"Role": f"{db.role}"}
            return did_work

        if db.is_free_tier:
            logger.debug("Don't operate on free ADB")
            did_work["No-op"] = {"Free": f"{db.is_free_tier}"}
            return did_work
        
        if db.is_dev_tier:
            logger.debug("Don't operate on Developer ADB")
            did_work["No-op"] = {"Dev": f"{db.is_dev_tier}"}
            return did_work        

        if db.lifecycle_state == "UNAVAILABLE":
            logger.debug("Don't operate on UNAVAILABLE DBs")
            did_work["No-op"] = {"Lifecycle": f"{db.lifecycle_state}"}

            return did_work

        # 1 - Model (Do this first)
        # Compute Model - to ECPU if necessary, otherwise check backup retention and adjust
        logger.debug(f'CPU Model: {db.compute_model} Count: {db.compute_count if db.compute_model == "OCPU" else db.compute_count}')
        if db.compute_model == "OCPU":

            # Actual Conversion
            logger.info(f'{">>>DRYRUN: " if dryrun else ""}Converting ECPU with {backup_retention} days retention for Autonomous DB: {db.display_name}')

            wait_for_available(db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        compute_model="ECPU"
                    )
                )
            # Waiting for AVAILABLE
            wait_for_available(db_id=db.id, start=False)

            did_work["ECPU"] = {"Convert": True}

            logger.info(f'{"DRYRUN: " if dryrun else ""}Converted ECPU Autonomous DB: {db.display_name}')

        # Rest of changes into one
        
        # Check backup retention and adjust

        # Start with blank update
        update_autonomous_database_details=UpdateAutonomousDatabaseDetails()
        updates_to_perform = False

        # 2 - Backup
        if db.backup_retention_period_in_days > backup_retention:
            update_autonomous_database_details.backup_retention_period_in_days = backup_retention
            logger.info(f'{"DRYRUN: " if dryrun else ""}Update Backup retention DB: {db.display_name} to configured {backup_retention} days')
            did_work["Backup"] = {"Retention": f"{backup_retention}"}
            updates_to_perform = True

        # 3 - Compute Reduce
        if db.compute_count > 2.0:
            update_autonomous_database_details.compute_count=2.0
            logger.info(f'{"DRYRUN: " if dryrun else ""}Update ECPU count: {db.display_name} from {db.compute_count} to 2.0')
            did_work["Compute"] = {"New ECPU": f"2.0"}
            updates_to_perform = True

        # 4 - Storage Scale
        # This only applies to ATP and AJD or APEX
        if db.db_workload == "OLTP" or db.db_workload == "AJD" or db.db_workload == "APEX":
            logger.debug(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs} Actual: {db.actual_used_data_storage_size_in_tbs} Allocated: {db.allocated_storage_size_in_tbs}")
            if db.data_storage_size_in_tbs:
            # Convert to GB or and scale down
                new_storage_gb = int(db.allocated_storage_size_in_tbs * 1024 * 2)
                new_storage_gb = 20 if new_storage_gb < 20 else new_storage_gb
                update_autonomous_database_details.data_storage_size_in_gbs = new_storage_gb
                update_autonomous_database_details.is_auto_scaling_for_storage_enabled=True
                did_work["Storage"] = {"Configured Storage": f"{new_storage_gb}"}
                updates_to_perform = True
                logger.info(f'{"DRYRUN: " if dryrun else ""}Scale Storage DB: {db.display_name} from {db.data_storage_size_in_tbs} TB to {new_storage_gb} GB (auto-scale)')

        # 5 - License Model - BYOL and SE
        if db.license_model == "LICENSE_INCLUDED":
            update_autonomous_database_details.license_model="BRING_YOUR_OWN_LICENSE"
            update_autonomous_database_details.database_edition="STANDARD_EDITION"
            logger.info(f'{"DRYRUN: " if dryrun else ""}Update License DB: {db.display_name} to BYOL / SE')
            did_work["License"] = {"BYOL": True, "SE": True}
            updates_to_perform = True

        # 6 - Tagging - require Schedule Tag
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
                    logger.info(f'{"DRYRUN: " if dryrun else ""}Not compliant({schedule_tag["AnyDay"]}) - will not stop - fixing')
                    current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}
                    update_autonomous_database_details.defined_tags = current_tags
                    did_work["Tag"] = {"update-default": True}
                    updates_to_perform = True

        else:
            # Add default tag to defined tags
            current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}
            update_autonomous_database_details.defined_tags = current_tags
            logger.info(f'{"DRYRUN: " if dryrun else ""}Adding Schedule Tags DB: {db.display_name} to Schedule / AnyDay Default')
            did_work["Tag"] = {"add-default": True}
            updates_to_perform = True

        # Perform work
        # Only do this is something is new
        if updates_to_perform:
            wait_for_available(db_id=db.id, start=True)
            # Say what we are doing
            logger.info(f'---Perform Work---')
            logger.info(f'{">>>DRYRUN: " if dryrun else ""}Work to perform: {db.display_name} \n{update_autonomous_database_details}')
            if not dryrun:
                database_client.update_autonomous_database(
                    update_autonomous_database_details=update_autonomous_database_details
                )
            logger.info(f'{">>>DRYRUN: " if dryrun else ""}Completed Work to: {db.display_name}')
        else:
            did_work["No-op"] = {"Actions": 0}


        # Return to initial state
        return_to_initial(db_id=db.id,initial=db_initial_lifecycle_state)
        logger.info(f'{">>>DRYRUN: " if dryrun else ""}Returned: {db.display_name} to initial state')

        # Complete
        logger.info(f'------')



        logger.info(f"----Complete ({db.display_name})----------")
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
    parser.add_argument("-w", "--writejson", help="output json", action="store_true")

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal
    region = args.region
    dryrun = args.dryrun
    threads = args.threads
    backup_retention = args.retention
    output_json = args.writejson

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger('oci-scale-atp')
    if verbose:
        logger.setLevel(logging.DEBUG)

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
        try:
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            # Create the OCI Client to use
            database_client = database.DatabaseClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)
        except ConfigFileNotFound as exc:
            logger.fatal(f"Unable to use Profile Authentication: {exc}")
            exit(1)

    # Main routine
        
    # Grab all ATP Serverless
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
            query='query autonomousdatabase resources'
        ),
        limit=1000
    ).data

    # Build a list of IDs
    db_ocids = []
    for i,db_it in enumerate(atp_db.items, start=1):
        db_ocids.append(db_it.identifier)

    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(database_work, db_ocids)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")
    
    # Write to file if desired, else just print
    if output_json:
        datestring = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
        filename = f'oci-atp-scale-down-{datestring}.json'
        with open(filename,"w") as outfile:
            outfile.write(json.dumps(results, indent=2))
            # for result in results:
            #     outfile.write(json.dumps(result, indent=2))

        logging.info(f"Script complete - wrote JSON to {filename}.")
    else:
        for result in results:
            logger.debug(f"Result: {result}")

