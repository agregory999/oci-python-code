from oci import config
from oci.database import DatabaseClient
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import argparse, time
from datetime import datetime, timedelta
import logging

# Create a default config using DEFAULT profile in default location
# Refer to
# https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm#SDK_and_CLI_Configuration_File
# for more info


# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-exa", "--exainfraocid", help="Exadata Infrastructure OCID", required=True)
parser.add_argument("-c", "--compartmentocid", help="Database Compartment OCID", required=True)
parser.add_argument("-ns", "--costtrackingns", help="Cost Tracking tag namespace", required=True)
parser.add_argument("-k", "--costtrackingkey", help="Cost Tracking tag key", required=True)
parser.add_argument("-d", "--daystoaverage", help="Days of data to analyze storage usage for", type=int, default=30)

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
frame_ns = args.costtrackingns
frame_key = args.costtrackingkey
exa_ocid = args.exainfraocid
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

#print(config["tenancy"],flush=True)

#exit(0)

# Set up OCI clients
database_client = DatabaseClient(config)
monitoring_client = MonitoringClient(config)

# Main Flow - start with Infra OCID to get name
# Script pulls Infra Detail, VM Cluster Detail (storage info)
# Then loops over all DBs and pulls details on storage used

# Get Infra
try:

    # Get Infra Detail
    rack = database_client.get_cloud_exadata_infrastructure(
        cloud_exadata_infrastructure_id=exa_ocid
    ).data

    print(f"Rack Detail: Comp:{rack.compute_count} Storage Count: {rack.storage_count} Total Storage(all ASM): {rack.total_storage_size_in_gbs} ID: {rack.id}", flush=True)

    # Apparantly not there yet
    # rack_unall = database_client.get_cloud_exadata_infrastructure_unallocated_resources(
    #     cloud_exadata_infrastructure_id=exa_id
    # ).data
    # print(f"Unall Detail: {rack_unall}",flush=True)

    # Cloud VM Cluster
    vm_cluster = database_client.list_cloud_vm_clusters(
        compartment_id=comp_ocid,
        cloud_exadata_infrastructure_id=rack.id
    ).data[0] # List of CloudVmClusterSummary - but only need first one of them

    # Try to get ExaCS Frame tag
    frame_tag = vm_cluster.defined_tags[frame_ns][frame_key]

    # Print DB ID and Tags
    print(f"VM Cluster Detail: {vm_cluster.display_name} Tags: {frame_tag} ID: {vm_cluster.id}", flush=True)

    # Total CPU and Storage
    rack_usable_storage = vm_cluster.storage_size_in_gbs * vm_cluster.data_storage_percentage * .01
    remaining_rack_usable_storage = rack_usable_storage
    print(f"Total OCPU: {vm_cluster.cpu_core_count} / Usable DATA Storage GB: {rack_usable_storage:.2f}",flush=True)

    # From ASM Metric
    # last 24 hours only
    end_time = datetime.now()
    start_time = end_time - timedelta(days = 1)
    summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
        compartment_id=comp_ocid,
        summarize_metrics_data_details=SummarizeMetricsDataDetails(
            namespace="oci_database_cluster",
            #query=f'StorageAllocatedByTablespace[1d]{{resourceId_database ="{db.id}" }}.mean()',
            query=f'ASMDiskgroupUtilization[1d]{{diskgroupName="ora.datac1.dg", resourceName="{vm_cluster.display_name}"}}.mean()',
            start_time=f"{start_time.isoformat()}Z",
            end_time=f"{end_time.isoformat()}Z",
            resolution="6h")
    ).data
    #print(f"Remaining Unused Storage GB (DATAC1 from ASM): {summarize_metrics_data_response}")
    print(f"Storage % consumed (DATAC1 from ASM): {summarize_metrics_data_response[0].aggregated_datapoints[0].value:.2f}")

    # For each database on rack, get min_cpu_count and storage used
    # Cloud VM Cluster
    databases = database_client.list_databases(
        compartment_id=comp_ocid,
        system_id=vm_cluster.id,
        limit=100
    ).data # List of DatabaseSummary

    for i,db in enumerate(databases,start=1):
        # DB Details

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

        # Add and average the datapoints - probably a better way to do this...
        print(f"{i}: DB: {db.db_unique_name}, Status: {db.lifecycle_state }")

        if summarize_metrics_data_response:
            print(f'{i} DB: {db.db_unique_name}')
            for j,ts in enumerate(summarize_metrics_data_response):
                sum = 0
                for dp in ts.aggregated_datapoints:
                    sum = sum + dp.value
                storage_used = sum / len(ts.aggregated_datapoints)
                
                # Decrement from total
                remaining_rack_usable_storage = remaining_rack_usable_storage - storage_used
                
                # Print summary
                print(f'    Storage Used GB: {storage_used:.2f}')
        else:
            print(f"    No Metrics for DB: {db.db_unique_name}")
        
        # Sleep a moment to give API some rest
        time.sleep(.5)
    # Print Remaining Storage (Decrement)
    print(f"Remaining Unused Storage GB: {remaining_rack_usable_storage:.2f}")


except ServiceError as exc:
    print(f"Failed to get details for {exa_ocid}: {exc}")



