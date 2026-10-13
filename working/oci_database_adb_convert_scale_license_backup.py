# ATP/ADW Scale down script
# Runs in region with Profile or Instance Principal
# Runs additional region with command line switch
# Use Multi-threading to deal with long-running tasks
# Dry Run feature to see what will actually happen without performing changes

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
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database.models import UpdateAutonomousDatabaseDetails
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, ResourceSummary
from oci.exceptions import ServiceError
from oci.exceptions import MaximumWaitTimeExceeded
from oci.exceptions import ConfigFileNotFound

import oci

# Constants
DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"
ECPU_MINIMUM = 2.0

# Wait_until callback - will report in debug mode on long-running wait
def cb(num, resp):
    # Get response
    db = resp.data
    logger.debug(f"Callback waiter: {num}, Name: {db.display_name} Lifecycle: {db.lifecycle_state}")

# Helper function - given an ADB OCID, will return when that DB is AVAILABLE
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
    
    # This may throw MaximumWaitTimeExceeded
    oci.wait_until(client=database_client, 
                   response=get_db_response,
                   property='lifecycle_state',
                   state='AVAILABLE',
                   max_wait_seconds=300,
                   max_interval_seconds=30,
                   wait_callback=cb)

    logger.debug(f"Autonomous DB: {db.display_name} AVAILABLE")

# Helper function - given an ADB OCID, return that DB to initial lifecycle state (if it was STOPPED)
def return_to_initial(db_id: str, initial:str):

    # Get updated status
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
    ).data

    # Stop the DB if it was already stopped
    if initial == "STOPPED" and db.lifecycle_state == "AVAILABLE":
        logger.info(f'{"DRYRUN: " if dryrun else ""}Stopping Autonomous DB: {db.display_name}')
        if dryrun:
            return
        # Actually stop the instance
        database_client.stop_autonomous_database(db.id)
        logger.debug(f"Kicked off STOP Autonomous for DB: {db.display_name} (Not Waiting)")

# Helper function - given an ADB OCID, perfrom the given update it
def perform_work(db_id: str, updates: UpdateAutonomousDatabaseDetails):
    wait_for_available(db_id=db_id, start=True)
    # Say what we are doing
    logger.info(f'---Perform Work on {db_id}---')
    logger.debug(f'{updates}')
    start_time = time.time()
    if not dryrun:
        database_client.update_autonomous_database(
            autonomous_database_id=db_id,
            update_autonomous_database_details=updates
        )
    wait_for_available(db_id=db_id, start=False)
    fin_time = time.time()
    logger.info(f'---End Work on {db_id} in {fin_time-start_time}s---')
    return (fin_time-start_time)

# Threaded work function
def database_work(db_id: str):

    # Get reference to ADB Instance
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
    ).data
    
    # Get Initial Lifecycle to return to afterwards
    db_initial_lifecycle_state = db.lifecycle_state
    
    # Set this boolean if anyhting is actually to be done
    updates_to_perform = False

    # Return Value is an empty JSON we will add to as work is done
    did_work = {}
    did_work["Detail"] = {"Name": f"{db.display_name}", "OCID": f"{db.id}", "Workload Type": f"{db.db_workload}", \
                          "Original CPU Model": f"{db.compute_model}", "Original License Model": f"{db.license_model}", \
                          "Original Backup Retention": f"{db.backup_retention_period_in_days}"
                        }

    # Now try the entire set of updates if required
    try:
        # Show before
        logger.info(f"----{db.db_workload} / {db.display_name}----------")
        logger.debug(f"OCID: {db_id}")
        logger.info(f'CPU Model: {db.compute_model} Dedicated: {db.is_dedicated} DG Role: {db.role} Free: {db.is_free_tier} Dev: {db.is_dev_tier}')
        logger.info(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs}")
        logger.info(f"License Model: {db.license_model} Edition: {db.database_edition} ")
        logger.debug(f"----{db_id}----Start ({db.display_name})----------")

        # Disqualify ADB instances that should not be touched
        if db.is_dedicated:
            logger.debug("Don't operate on dedicated")
            did_work["No-op"] = {"Dedicated": True}
            return did_work

        if db.role == "BACKUP_COPY" or db.lifecycle_state == "STANDBY":
            logger.debug("Don't operate on anything but primary")
            did_work["No-op"] = {"Role": f"{db.role}"}
            return did_work

        if db.is_free_tier:
            logger.debug("Don't operate on free ADB")
            did_work["No-op"] = {"Free Tier": f"{db.is_free_tier}"}
            return did_work
        
        if db.is_dev_tier:
            logger.debug("Don't operate on Developer ADB")
            did_work["No-op"] = {"Dev Tier": f"{db.is_dev_tier}"}
            return did_work        

        if db.lifecycle_state == "UNAVAILABLE":
            logger.debug("Don't operate on UNAVAILABLE DBs")
            did_work["No-op"] = {"Lifecycle": f"{db.lifecycle_state}"}
            return did_work

        # 1 - Model (Do this first)
        # Compute Model - to ECPU if necessary, otherwise check backup retention and adjust
        logger.debug(f'CPU Model: {db.compute_model} Count: {db.compute_count if db.compute_model == "OCPU" else db.compute_count}')
        if db.compute_model == "OCPU":

            # Change the compute model to ECPU, required before doing other things
            logger.info(f'{"DRYRUN: " if dryrun else ""}Converting to ECPU model for Autonomous DB: {db.display_name}')
            time_taken = perform_work(db.id, UpdateAutonomousDatabaseDetails(compute_model="ECPU"))
            did_work["ECPU"] = {"Convert": True, "Time": time_taken}
            updates_to_perform = True
        
        # Check backup retention and adjust
        # 2 - Backup
        if db.backup_retention_period_in_days > backup_retention:

            # Change the backup retention to the configured retention
            logger.info(f'{"DRYRUN: " if dryrun else ""}Update Backup retention DB: {db.display_name} to configured {backup_retention} days')
            time_taken = perform_work(db.id, UpdateAutonomousDatabaseDetails(backup_retention_period_in_days = backup_retention))
            did_work["Backup"] = {"Retention": f"{backup_retention}", "Time": time_taken}
            updates_to_perform = True

        # 3 - Compute Reduce
        if db.compute_count > ECPU_MINIMUM:

            # Change the backup retention to the configured retention
            logger.info(f'{"DRYRUN: " if dryrun else ""}Update ECPU count: {db.display_name} from {db.compute_count} to {ECPU_MINIMUM}')
            time_taken = perform_work(db.id, UpdateAutonomousDatabaseDetails(compute_count=ECPU_MINIMUM))
            did_work["Compute"] = {"New ECPU": f"{ECPU_MINIMUM}", "Time": time_taken}
            updates_to_perform = True

        # 4 - Storage Scale
        # This only applies to ATP and AJD or APEX
        if db.db_workload == "OLTP" or db.db_workload == "AJD" or db.db_workload == "APEX":
            logger.debug(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs} Actual: {db.actual_used_data_storage_size_in_tbs} Allocated: {db.allocated_storage_size_in_tbs}")
            if db.data_storage_size_in_tbs:
            # Convert to GB or and scale down
                new_storage_gb = int(db.allocated_storage_size_in_tbs * 1024 * 2)
                new_storage_gb = 20 if new_storage_gb < 20 else new_storage_gb
                
                # Change the storage to 2x the in use amount and enable auto-scale
                logger.info(f'{"DRYRUN: " if dryrun else ""}Scale Storage DB: {db.display_name} from {db.data_storage_size_in_tbs} TB to {new_storage_gb} GB (auto-scale)')
                time_taken = perform_work(db.id, UpdateAutonomousDatabaseDetails(
                    data_storage_size_in_gbs = new_storage_gb,
                    is_auto_scaling_for_storage_enabled=True)
                )

                did_work["Storage"] = {"Configured Storage": f"{new_storage_gb}", "Time": time_taken}
                updates_to_perform = True

        # 5 - License Model - BYOL and SE
        # This only applies to ATP and ADW
        if db.db_workload == "OLTP" or db.db_workload == "DW":
            if db.license_model == "LICENSE_INCLUDED":
                time_taken = perform_work(db.id, 
                                          UpdateAutonomousDatabaseDetails(
                                              license_model="BRING_YOUR_OWN_LICENSE",
                                              database_edition="STANDARD_EDITION"
                                              )
                                        )

                logger.info(f'{"DRYRUN: " if dryrun else ""}Update License DB: {db.display_name} to BYOL / SE')
                did_work["License"] = {"BYOL": True, "SE": True, "Time": time_taken}
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
                    time_taken = perform_work(db.id, UpdateAutonomousDatabaseDetails(defined_tags = current_tags))
                    did_work["Tag"] = {"update-default": True, "Time": time_taken}
                    updates_to_perform = True

        else:
            # Add default tag to defined tags
            current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}
            time_taken = perform_work(db.id, UpdateAutonomousDatabaseDetails(defined_tags = current_tags))
            logger.info(f'{"DRYRUN: " if dryrun else ""}Adding Schedule Tags DB: {db.display_name} to Schedule / AnyDay Default')
            did_work["Tag"] = {"add-default": True}
            updates_to_perform = True

        # If there were no updates, add a No-op to the JSON
        if not updates_to_perform:
            did_work["No-op"] = {"Actions": 0}

        # Return to initial state
        return_to_initial(db_id=db.id,initial=db_initial_lifecycle_state)
        logger.info(f'{"DRYRUN: " if dryrun else ""}Returned: {db.display_name} to initial state')
        logger.info(f"----Complete ({db.display_name})----------")
    except ServiceError as exc:
        logger.warning(f"Failed to complete action for DB: {db.display_name} \nReason: {exc}")
        did_work["Error"] = {"Exception": exc.message}
    except MaximumWaitTimeExceeded as exc:
        logger.warning(f"Timed out for DB: {db.display_name} \nReason: {exc}")
        did_work["Error"] = {"Exception": str(exc)}

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
        else:
            region = signer.region

        database_client = database.DatabaseClient(config=config_ip, signer=signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        search_client = ResourceSearchClient(config=config_ip, signer=signer)
    else:
        # Use a profile (must be defined or DEFAULT)
        try:
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            if region:
                config["region"] = region
                logger.info(f"Changing region to {region}")
            else:
                region = config["region"]
            # Create the OCI Client to use
            database_client = database.DatabaseClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)
        except ConfigFileNotFound as exc:
            logger.fatal(f"Unable to use Profile Authentication: {exc}")
            exit(1)

    # Main routine
        
    # Grab all ADB (ADW, ATP, APEX, AJD)
    # Loop through
    # Ensure:
    # 1) Updated to ECPU
    # 2) License is BYOL / Standard
    # 3) Storage is scaled down
    # 4) Tags for AnyDay are there and not 1,1,1


    # Get ADB via Resource Search
    atp_db = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query autonomousdatabase resources'
            # Example below to limit to a specific ADB Type
            #query='query autonomousdatabase resources return allAdditionalFields where (workloadType="ADW")'
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
        filename = f'oci-atp-scale-down-{region}-{datestring}.json'
        with open(filename,"w") as outfile:
            # Take the entire JSON and dump with indent
            outfile.write(json.dumps(list(results), indent=2))

        logging.info(f"Script complete - wrote JSON to {filename}.")
    else:
        # Output JSON in debug:
        logger.debug(f"Result: {json.dumps(list(results), indent=2)}")

