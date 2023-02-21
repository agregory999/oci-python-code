from oci import config
from oci.database import DatabaseClient
from oci.exceptions import ServiceError

import argparse, time
from datetime import datetime, timedelta
import logging

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
    logging.getLogger('oci').setLevel(logging.DEBUG)
print(f"Using profile {profile}.")
print(f'Showing all backups in Compartment {comp_ocid}')

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Set up OCI clients
database_client = DatabaseClient(config)

# Main Flow - start with Comp OCID to get DBs
# Script pulls DB Backup Detail

# Main loop
try:

    # Cloud VM Cluster
    vm_clusters = database_client.list_cloud_vm_clusters(
        compartment_id=comp_ocid,
    ).data # List of CloudVmClusterSummary - but only need first one of them

    for vmc in vm_clusters:
        # For each database in cluster, get min_cpu_count and storage used
        # Cloud VM Cluster
        databases = database_client.list_databases(
            compartment_id=comp_ocid,
            system_id=vmc.id,
            limit=100
        ).data # List of DatabaseSummary

        for db in databases:
            # For each DB, get the backups
            backups = database_client.list_backups(
                database_id=db.id
            ).data

            # Show backups
            for backup in backups:
                duration = backup.time_ended - backup.time_started
                print(f'VMC: {vmc.cluster_name} DB: {db.db_unique_name}: Backup OCID: {backup.id} Backup Type: {backup.type} Lifecycle: {backup.lifecycle_state} {backup.lifecycle_details if backup.lifecycle_state=="FAILED" and backup.lifecycle_details else ""} Time(finished): {backup.time_ended.strftime("%Y-%m-%d %H:%M:%S")} Duration(sec) {duration.total_seconds()}', flush=True)
except ServiceError as exc:
    print(f"Failed to get details: {exc}")
        
