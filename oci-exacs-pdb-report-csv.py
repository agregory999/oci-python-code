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
output_file_name = f'pdb-report-{time.strftime("%Y%m%d-%H%M%S")}-{comp_ocid}.csv'
temp_file_name = f'/tmp/{output_file_name}'

# Open the file for writing
with open(temp_file_name, 'w', newline='') as csvfile:
    # Set up CSV
    csv_writer = csv.writer(csvfile, delimiter='^',
                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(["VMC_OCID","VMC_NAME","CDB_OCID","CDB_NAME","CDB_LIFECYCLE","STORAGE_CDB","MIN_CPU_CDB","PDB_OCID","PDB_NAME","PDB_STORAGE","MIN_CPU_PDB"])

    # Get Infra
    try:

        # For each database in cluster, get min_cpu_count and storage used
        # Cloud VM Cluster
        databases = database_client.list_pluggable_databases(
            compartment_id=comp_ocid, 
            limit=100
        ).data # List of DatabaseSummary

        # # Get all VM Clusters
        # vm_clusters = database_client.list_cloud_vm_clusters(
        #     compartment_id=comp_ocid
        # ).data # List of CloudVmClusterSummary - but only need first one of them

        # # For each cluster, get DB
        # for cluster in vm_clusters:

            # # For each database in cluster, get min_cpu_count and storage used
            # # Cloud VM Cluster
            # databases = database_client.list_databases(
            #     compartment_id=comp_ocid, 
            #     system_id=cluster.id,
            #     limit=100
            # ).data # List of DatabaseSummary

        for pdb in databases:
            # CDB Details
            cdb = database_client.get_database(
                database_id=pdb. container_database_id
            ).data
            # VMC Details
            vm_cluster = database_client.get_cloud_vm_cluster(
                cloud_vm_cluster_id=cdb.vm_cluster_id
            ).data
       
            print(f"VMC: {vm_cluster.display_name} DB: {cdb.db_unique_name}, Status: {cdb.lifecycle_state} RO: {pdb.open_mode}")

            # CDB Storage
            # Storage in use / Metric / XX day average of average storage used
            # StorageUsed[1d]{resourceId_database = "DB OCID"}.mean()
            end_time = datetime.now()
            start_time = end_time - timedelta(days = days_to_average)
            cdb_summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
                compartment_id=comp_ocid,
                summarize_metrics_data_details=SummarizeMetricsDataDetails(
                    namespace="oracle_oci_database",
                    query=f'StorageUsed[12h]{{resourceId="{cdb.id}" }}.max()',
                    start_time=f"{start_time.isoformat()}Z",
                    end_time=f"{end_time.isoformat()}Z"
                )
            ).data

            # PDB Storage
            # Storage in use / Metric / XX day average of average storage used
            # StorageUsed[1d]{resourceId_database = "DB OCID"}.mean()
            end_time = datetime.now()
            start_time = end_time - timedelta(days = days_to_average)
            pdb_summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
                compartment_id=comp_ocid,
                summarize_metrics_data_details=SummarizeMetricsDataDetails(
                    namespace="oracle_oci_database",
                    query=f'StorageUsed[12h]{{resourceId="{pdb.id}" }}.max()',
                    start_time=f"{start_time.isoformat()}Z",
                    end_time=f"{end_time.isoformat()}Z"
                )
            ).data

            #print(f"Output PDB: {pdb_summarize_metrics_data_response}")
            pdb_cpu_count = None
            cdb_cpu_count = None
            error = ""
            try:
                # Get PDB Param from DBM
                dbm_parameter_response = dbm_client.list_database_parameters(
                    managed_database_id=pdb.id,
                    name="cpu_min_count"
                ).data
                pdb_cpu_count = float(dbm_parameter_response.items[0].value) if dbm_parameter_response and len(dbm_parameter_response.items) > 0 else None
                print(f"   Type: {dbm_parameter_response.database_type} CPU_MIN_Count: {dbm_parameter_response.items[0].value}")
            except ServiceError as exc:
                print(f"   Failed to get details: {exc.status}, {exc.message}")
                error += exc.message
            except IndexError as exc:
                print(f"   Failed to get details: {exc}")
            try:
                # Get CDB Param from DBM
                dbm_parameter_response = dbm_client.list_database_parameters(
                    managed_database_id=cdb.id,
                    name="cpu_min_count"
                ).data
                cdb_cpu_count = float(dbm_parameter_response.items[0].value) if dbm_parameter_response and len(dbm_parameter_response.items) > 0 else None
                print(f"   Type: {dbm_parameter_response.database_type} CPU_MIN_Count: {dbm_parameter_response.items[0].value}")
            except ServiceError as exc:
                print(f"   Failed to get details: {exc.status}, {exc.message}")
                error += exc.message
            except IndexError as exc:
                print(f"   Failed to get details: {exc}")
            # Add and average the datapoints - probably a better way to do this...

            cdb_storage_used = -1
            if cdb_summarize_metrics_data_response:
                sum = 0
                for dp in cdb_summarize_metrics_data_response[0].aggregated_datapoints:
                    sum = sum + dp.value
                cdb_storage_used = sum / len(cdb_summarize_metrics_data_response[0].aggregated_datapoints)

                #storage_used = summarize_metrics_data_response[0].aggregated_datapoints[0].value
                print(f'   Storage (CDB {cdb.db_unique_name}): {cdb_storage_used:.2f}')
            pdb_storage_used = -1
            if pdb_summarize_metrics_data_response:
                sum = 0
                for dp in pdb_summarize_metrics_data_response[0].aggregated_datapoints:
                    sum = sum + dp.value
                pdb_storage_used = sum / len(pdb_summarize_metrics_data_response[0].aggregated_datapoints)

                #storage_used = summarize_metrics_data_response[0].aggregated_datapoints[0].value
                print(f'   Storage (PDB {pdb.pdb_name}): {pdb_storage_used:.2f}')
            # Sleep a moment to give API some rest
            time.sleep(.2)
            # Write row to CSV
            #csv_writer.writerow([vm_cluster.id,vm_cluster.display_name,cdb.id,cdb.db_unique_name,cdb.lifecycle_state,f"{storage_used:.2f}",cdb_cpu_count if cdb_cpu_count else "n/a",pdb.id,pdb.pdb_name,pdb_cpu_count if pdb_cpu_count else "n/a",error])
            csv_writer.writerow([vm_cluster.id,vm_cluster.display_name,cdb.id,cdb.db_unique_name,cdb.lifecycle_state,f"{cdb_storage_used:.2f}",cdb_cpu_count if cdb_cpu_count else "n/a",pdb.id,pdb.pdb_name,f"{pdb_storage_used:.2f}",pdb_cpu_count if pdb_cpu_count else "n/a"])

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
