# ATP Scale down script
# Runs in region with instance Principal
# Runs additional region with profile

# Written by Andrew Gregory
# 2/13/2024 v1

# Generic Imports
import argparse
import logging    # Python Logging

# OCI Imports
from oci import config
from oci import database
from oci import identity
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database.models import UpdateAutonomousDatabaseDetails
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, ResourceSummary
from oci.exceptions import ServiceError

import oci

# Constants
DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"

# Helper function
def wait_for_available(dryrun:bool, database_client:database.DatabaseClient, db_id: str, start:bool):

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

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
parser.add_argument("--dryrun", help="Dry Run - no action", action="store_true")

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
use_instance_principals = args.instanceprincipal
dryrun = args.dryrun

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('oci-scale-atp')
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

# Client creation
if use_instance_principals:
    print(f"Using Instance Principal Authentication")
    signer = InstancePrincipalsSecurityTokenSigner()
    database_client = database.DatabaseClient(config={}, signer=signer)
    search_client = ResourceSearchClient(config={}, signer=signer)
else:
    # Use a profile (must be defined)
    print(f"Using Profile Authentication: {profile}")
    config = config.from_file(profile_name=profile)

    # Create the OCI Client to use
    database_client = database.DatabaseClient(config)
    search_client = ResourceSearchClient(config)

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
        query='query autonomousdatabase resources return allAdditionalFields where (workloadType="ATP")'
    ),
    limit=1000
).data

# Iterate all ATP
for i,db_it in enumerate(atp_db.items, start=1):
    # logger.debug(f"**{i}**DB: {db_it}")
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_it.identifier
    ).data

    try:
        # Show before
        logger.info(f"----{i}----Examine ({db.display_name} / {db.id})----------")
        logger.info(f'CPU Model: {db.compute_model} Dedicated: {db.is_dedicated} DG Role: {db.role}')
        logger.info(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs}")
        logger.info(f"License Model: {db.license_model} Edition: {db.database_edition} ")
        logger.info(f"----{i}----Start ({db.display_name})----------")

        if db.is_dedicated:
            logger.debug("Don't operate on dedicated")
            continue

        logger.debug(db)

        if db.role == "STANDBY":
            logger.debug("Don't operate on anything but primary")
            continue

        # Compute Model - to ECPU
        logger.debug(f'CPU Model: {db.compute_model} Count: {db.compute_count if db.compute_model == "OCPU" else db.compute_count}')
        if db.compute_model == "OCPU":

            # Actual Conversion
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Converting ECPU Autonomous DB: {db.display_name}')

            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        backup_retention_period_in_days=15,
                        compute_model="ECPU"
                        )
                )
            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Converted ECPU Autonomous DB: {db.display_name}')

        # Storage - scale to GB
        logger.debug(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs} Actual: {db.actual_used_data_storage_size_in_tbs} Allocated: {db.allocated_storage_size_in_tbs}")
        if not db.data_storage_size_in_tbs:
            logger.debug(f"Storage in GB Model - no action")
        else:
            # Figure out storage
            # Existing TB * 1024 (conversion) * 2 (allow extra)
            new_storage_gb = int(db.allocated_storage_size_in_tbs * 1024 * 2)
            new_storage_gb = 20 if new_storage_gb < 20 else new_storage_gb
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Scale Storage DB: {db.display_name} from {db.data_storage_size_in_tbs} TB to {new_storage_gb} GB (auto-scale)')

            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            # Actual scaling (2 ECPU, auto-scale, Storage auto-scale)
            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        is_auto_scaling_for_storage_enabled=True,
                        data_storage_size_in_gbs=new_storage_gb,
                        compute_count=2.0,
                        is_auto_scaling_enabled=True

                    )
                )
            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Scale Storage DB: {db.display_name} completed')

        # License Model - BYOL and SE
        if db.license_model == "LICENSE_INCLUDED":
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Update License DB: {db.display_name} to BYOL / SE')

            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        license_model="BRING_YOUR_OWN_LICENSE",
                        database_edition="STANDARD_EDITION"
                    )
                )
            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

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
                    current_tags["Schedule"] = {"AnyDay" : "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"}

                    # Start and wait if needed
                    wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

                    if not dryrun:
                        database_client.update_autonomous_database(
                            autonomous_database_id=db.id,
                            update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                                defined_tags=current_tags
                            )
                        )
                    wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

        else:
            # Add default tag to defined tags
            current_tags["Schedule"] = {"AnyDay" : "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"}

            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Updating Tags DB: {db.display_name} to Schedule / AnyDay Default')

            # Start and wait if needed
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        defined_tags=current_tags
                    )
                )

            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Updated Tags DB: {db.display_name} to Schedule / AnyDay Default')

        logger.info(f"----{i}----Complete ({db.display_name})----------")
    except ServiceError as exc:
        logger.error(f"Failed to complete action for DB: {db_it} \nReason: {exc}")
    # End main loop