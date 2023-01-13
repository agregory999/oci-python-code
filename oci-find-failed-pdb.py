from oci import config
from oci.database import DatabaseClient
from oci.monitoring import MonitoringClient
from oci.secrets import SecretsClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import argparse, time
import logging


# Logging
logging.basicConfig
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-c", "--compartmentocid", help="Database Compartment OCID", required=True)

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
comp_ocid = args.compartmentocid

# If required, verbose
if verbose:
    print(f'Using verbose mode')
    logger.setLevel(logging.DEBUG)

logger.debug(f"Using profile {profile}.")

# Initialize service client with default config file
config = config.from_file(profile_name=profile)
logger.info(f'Connecting to OCI {config["tenancy"]}.')


# Set up OCI clients
database_client = DatabaseClient(config)
monitoring_client = MonitoringClient(config)
secrets_client = SecretsClient(config)

# Main Flow - start with Compartment OCID
# Script pulls PDB Info.  If failed, grab CDB Info and display UI remediation info

try:

    # Get all VM Clusters
    vm_clusters = database_client.list_cloud_vm_clusters(
        compartment_id=comp_ocid
    ).data # List of CloudVmClusterSummary - but only need first one of them

    # For each cluster, get DB
    for cluster in vm_clusters:

        # Get PDBs
        databases = database_client.list_pluggable_databases(
            compartment_id=comp_ocid, 
            limit=1000
        ).data # List of DatabaseSummary

        # Loop over PDB
        for pdb in databases:
            # DB Details if verbose
            logger.debug(f"CDB: {pdb.container_database_id} PDB: {pdb.pdb_name}, Status: {pdb.lifecycle_state}")

            # Only print detail if failed
            if pdb.lifecycle_state == "FAILED":
                cdb = database_client.get_database(
                    database_id=pdb.container_database_id
                ).data # Database
                logger.warning("----------------")
                logger.warning(f"Failed PDB: {pdb.pdb_name} / {pdb.lifecycle_state} \n  CDB: {cdb.db_unique_name}  \n  CDB Lifecycle: {cdb.lifecycle_state}\n  PDB Lifecycle: {pdb.lifecycle_details}")

            # Sleep a moment to give API some rest
            time.sleep(.5)

except ServiceError as exc:
    print(f"Failed to get details: {exc}")
