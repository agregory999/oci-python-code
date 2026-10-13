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
from oci.database.models import DatabaseSummary, PluggableDatabaseSummary
from oci import pagination

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
import csv

def write_row():
    # Write Row
    # A-I, J-V W-AF AG-AO
    logger.info(f"Write Row: {guid}-{db_name}")
    csv_writer.writerow([guid,db_name,"oracle_database",db_type,"","","","",db_name,\
        "","","19c",host_name,"","",db.character_set,"",role,"","","","",\
        "Linux","Intel","","","","1",enabled_ocpu,"YES","","",\
        cluster_display,environment,tag,"","","","","",""])

# PHASE 1 - Parsing of Arguments, Python Logging
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
parser.add_argument("-o", "--compartmentocid", help="Compartment OCID, required", required=True)
parser.add_argument("-vmc", "--vmcocids", help="VM Cluster OCID, comma separated, required", nargs="+", required=True)
parser.add_argument("-g", "--guidstart", help="GUID Start (default 1)", type=int, default=1)
parser.add_argument("-e", "--environment", help="Enviroment (NONPROD,PROD)", default="NONPROD")

args = parser.parse_args()
verbose = args.verbose  # Boolean
profile = args.profile  # String
use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
region = args.region # Region to use with Instance Principal, if not default
comp_ocid = args.compartmentocid # String
vmc_ocids = args.vmcocids # String
guid = args.guidstart #int
environment = args.environment # String

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')
logger.debug(f"debug test - compartment OCID: {comp_ocid}")

# PHASE 2 - Creation of OCI Client(s) 

# Connect to OCI with DEFAULT or defined profile
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

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        database_client = DatabaseClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

except ClientError as ex:
    logger.critical(f"Failed to connect to OCI: {ex}")

# Create any necessary Clients
db_client = DatabaseClient(config)

# PHASE 3 - Main Script Execution

# Get PDBs Example
try:

    pdb_databases = pagination.list_call_get_all_results(
        database_client.list_pluggable_databases,
        compartment_id=comp_ocid
    ).data


    # pdb_databases = database_client.list_pluggable_databases(
    #     compartment_id=comp_ocid,
    # ).data # List of PluggableDatabaseSummary

    logger.info(f"Found {len(pdb_databases)} PDB ")
    # Parse Data
    with open("pdb.csv", 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile, delimiter=',',
                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for pdb in pdb_databases:
            logger.debug(f"PDB: {pdb.pdb_name} OCI: {pdb.id}, Status: {pdb.lifecycle_state} OPen Mode: {pdb.open_mode}")
            csv_writer.writerow([pdb.pdb_name,pdb.lifecycle_state,pdb.open_mode,pdb.container_database_id])
            #logger.debug(f"Full Details: {pdb}")
except ServiceError as ex:
    logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
    logger.debug(f"Full Exception Detail: {ex}")

# Do this with CSV
with open("oee.csv", 'w', newline='') as csvfile:
    # Set up CSV
    csv_writer = csv.writer(csvfile, delimiter=',',
                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
    # DB_TARGET_GUID	DB_TARGET_NAME	DB_TARGET_TYPE	DB_TYPE	DB_NAME	DB_VERSION	DB_HOST_NAME	DB_STANDBY_ROLE	DB_HOST_OPERATING_SYSTEM	DB_HOST_CPU_VENDOR	DB_HOST_CPU_COUNT	DB_HOST_CPU_CORES	DB_HOST_CPU_HYPERTHREADING	DB_HOST_METRICS_DATE	DB_NORMAL_CREDS	DB_LOCATION	DB_ENVIRONMENT	DB_APPLICATION	DB_SUBSCRIPTION	DB_BUSINESS_UNIT	DB_PLATFORM	DB_STATUS	DATA_SOURCE	EXTRACT_DATE
										
    csv_writer.writerow(["DB_TARGET_GUID","DB_TARGET_NAME","DB_TARGET_TYPE","DB_TYPE","DB_PLUGGABLE_COUNT","DB_CONTAINER_TARGET_GUID","DB_CONTAINER_TARGET_NAME","DB_CONTAINER_TARGET_TYPE","DB_NAME","DB_GLOBAL_NAME","DB_PDB_NAME","DB_VERSION","DB_HOST_NAME","DB_INSTANCE_NAME","DB_LOG_MODE","DB_CHARACTERSET","DB_NATIONAL_CHARACTERSET","DB_STANDBY_ROLE","DB_STANDBY_UNIQUE_NAME","DB_PRIMARY_UNIQUE_NAME","DB_PRIMARY_TARGET_GUID","DB_METRICS_DATE","DB_HOST_OPERATING_SYSTEM","DB_HOST_CPU_VENDOR","DB_HOST_CPU_FREQUENCY","DB_HOST_CPU_IMPLEMENTATION","DB_HOST_CPU_REVISION","DB_HOST_CPU_COUNT","DB_HOST_CPU_CORES","DB_HOST_CPU_HYPERTHREADING","DB_HOST_METRICS_DATE","DB_NORMAL_CREDS","DB_LOCATION","DB_ENVIRONMENT","DB_APPLICATION","DB_SUBSCRIPTION","DB_BUSINESS_UNIT","DB_PLATFORM","DB_STATUS","DATA_SOURCE","EXTRACT_DATE"])

    # For each VM Cluster
    for vmc_ocid in vmc_ocids:
        # Get VM Cluster name, enabled OCPU
        vmc = database_client.get_cloud_vm_cluster(
            cloud_vm_cluster_id=vmc_ocid
        ).data
        host_name = vmc.hostname
        enabled_ocpu = int(vmc.ocpu_count)
        cluster_display = vmc.display_name

        # Get DBs, output if non-CDB, if CDB, list PDBs
        try:
            databases = database_client.list_databases(
                compartment_id=comp_ocid,
                system_id=vmc_ocid,
                limit=1000
            ).data # List of DatabaseSummary

            # Parse Data
            for db in databases:
                # # Don't care about anything but active
                # if db.lifecycle_state != DatabaseSummary.LIFECYCLE_STATE_AVAILABLE:
                #     logger.info(f"Ignore {db.db_name} Lifecycle: {db.lifecycle_state}")
                #     continue

                # Reset Role
                role = "PRIMARY"

                logger.info(f"Processing {db.db_name}")

                if db.is_cdb:
                    cdb_id = db.id

                    # Basic Name / type
                    db_type = "PLUGGABLE (RAC)"

                    # Tag
                    tag = "n/a"

                    # Count PDB
                    pdb_found = 0

                    # query PDBs
                    for pdb in pdb_databases:
                        #if pdb.lifecycle_state == PluggableDatabaseSummary.LIFECYCLE_STATE_AVAILABLE and pdb.container_database_id == cdb_id:
                        if pdb.container_database_id == cdb_id:

                            db_name = f"{db.db_unique_name}.{pdb.pdb_name}"

                            try:
                                tag = pdb.defined_tags["Windstream_Tags"]["Application_Name"]

                                # Role
                                if pdb.open_mode != "READ_WRITE":
                                    role = "STANDBY"
                            except KeyError as e:
                                logger.debug(f"Bad key {e}")
                            # Output
                            logger.debug(f"Write Row (PDB): {guid}-{db_name}")
                            write_row()
                            # Increment GUID
                            guid += 1
                            pdb_found += 1

                    # Handle empty CDB (we don't care about those)
                    if pdb_found == 0:
                        logger.info(f"Skipping empty CDB: {db.db_unique_name}")
                        logger.debug(f"Skipping empty CDB: {db.db_unique_name} Debug: {db}")
                        continue
                else:
                    # Basic Name / Type
                    db_name = f"{db.db_unique_name}"
                    db_type = "NON-MULTITENANT (RAC)"

                    # Tag
                    tag = "n/a"
                    try:
                        tag = db.defined_tags["Windstream_Tags"]["Application_Name"]
                    except KeyError as e:
                        pass

                    # Write Row
                    # A-I, J-V W-AF AG-AO
                    logger.debug(f"Write Row (CDB): {guid}-{db_name}")
                    write_row()

                    # Increment GUID
                    guid = guid + 1

                #logger.debug(f"Full Details: {pdb}")
        except ServiceError as ex:
            logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
            logger.debug(f"Full Exception Detail: {ex}")

        

