from oci import config
from oci.database import DatabaseClient
from oci.monitoring import MonitoringClient
from oci.database_management import DbManagementClient
from oci.database_management.models import DatabaseParametersCollection
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import argparse, time
from datetime import datetime, timedelta
import logging
import csv
import os

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-c", "--compartmentocid", help="Database Compartment OCID", required=True)
parser.add_argument("-d", "--daystoaverage", help="Days of data to analyze storage usage for", type=int, default=30)

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
comp_ocid = args.compartmentocid
days_to_average = args.daystoaverage

# If required, verbose
if verbose:
    print(f'Using verbose mode')
    logging.getLogger('oci').setLevel(logging.DEBUG)
print(f"Using profile {profile}.")
print(f'Using {days_to_average} days of data to analyze storage')

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Set up OCI clients
database_client = DatabaseClient(config)
monitoring_client = MonitoringClient(config)
dbm_client = DbManagementClient(config)

# Main Flow - start with Infra OCID to get name
# Script pulls Infra Detail, VM Cluster Detail (storage info)
# Then loops over all DBs and pulls details on storage used

# Define file name(s)
output_file_name = f'storage-used-{time.strftime("%Y%m%d-%H%M%S")}-{comp_ocid}.csv'
temp_file_name = f'/tmp/{output_file_name}'

# Open the file for writing
with open(temp_file_name, 'w', newline='') as csvfile:
    # Set up CSV
    csv_writer = csv.writer(csvfile, delimiter='^',
                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
    # Get Infra
    try:

        # Get all VM Clusters
        vm_clusters = database_client.list_cloud_vm_clusters(
            compartment_id=comp_ocid
        ).data # List of CloudVmClusterSummary - but only need first one of them

        # For each cluster, get DB
        for cluster in vm_clusters:

            # For each database in cluster, get min_cpu_count and storage used
            # Cloud VM Cluster
            databases = database_client.list_databases(
                compartment_id=comp_ocid, 
                system_id=cluster.id,
                limit=100
            ).data # List of DatabaseSummary

            for db in databases:
                # DB Details
                print(f"VMC: {cluster.display_name} DB: {db.db_unique_name}, Status: {db.lifecycle_state}")

                # Storage in use / Metric / XX day average of average storage used
                # StorageUsed[1d]{resourceId_database = "DB OCID"}.mean()
                end_time = datetime.now()
                start_time = end_time - timedelta(days = days_to_average)
                summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
                    compartment_id=comp_ocid,
                    summarize_metrics_data_details=SummarizeMetricsDataDetails(
                        namespace="oci_database",
                        #query=f'StorageAllocatedByTablespace[1d]{{resourceId_database ="{db.id}" }}.mean()',
                        query=f'StorageUsed[1d]{{resourceId_database ="{db.id}" }}.mean()',
                        start_time=f"{start_time.isoformat()}Z",
                        end_time=f"{end_time.isoformat()}Z",
                        resolution="6h")
                ).data
                
                cpu_count = None
                try:
                    # Get Param from DBM
                    dbm_parameter_response = dbm_client.list_database_parameters(
                        managed_database_id=db.id,
                        name="cpu_min_count"
                    ).data
                    cpu_count = float(dbm_parameter_response.items[0].value) if dbm_parameter_response and len(dbm_parameter_response.items) > 0 else None
                    print(f"   Type: {dbm_parameter_response.database_type} CPU_Count: {dbm_parameter_response.items[0].value}")
                except ServiceError as exc:
                    print(f"   Failed to get details: {exc.status}, {exc.message}")

                # Add and average the datapoints - probably a better way to do this...

                if summarize_metrics_data_response:
                    sum = 0
                    for dp in summarize_metrics_data_response[0].aggregated_datapoints:
                        sum = sum + dp.value
                    storage_used = sum / len(summarize_metrics_data_response[0].aggregated_datapoints)

                    #storage_used = summarize_metrics_data_response[0].aggregated_datapoints[0].value
                    print(f'   {storage_used:.2f}')
                    csv_writer.writerow([cluster.id,cluster.display_name,db.id,db.db_unique_name,db.lifecycle_state,f"{storage_used:.2f}",cpu_count if cpu_count else "n/a"])
                else:
                    csv_writer.writerow([cluster.id,cluster.display_name,db.id,db.db_unique_name,db.lifecycle_state,-1,cpu_count if cpu_count else "n/a"])
                # Sleep a moment to give API some rest
                time.sleep(.5)

    except ServiceError as exc:
        print(f"Failed to get details: {exc}")

# Re-open /tmp output &
# Open the file for writing
with open(temp_file_name, 'r', newline='') as csvfile_read:
    with open(output_file_name, 'w', newline='') as newfile_write:
        file = csvfile_read.readlines()
        for line in file:
            newfile_write.write(str.replace(line,'^',' | '))
    newfile_write.close
csvfile_read.close

# Delete temp file
os.remove(temp_file_name)           
