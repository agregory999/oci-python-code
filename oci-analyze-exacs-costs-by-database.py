from oci import config
from oci.database_management import DbManagementClient
from oci.usage_api import UsageapiClient
from oci.usage_api.models import RequestSummarizedUsagesDetails,Filter,Dimension,Tag
from oci.database import DatabaseClient
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import os, time
from datetime import datetime, timedelta
import logging

# Create a default config using DEFAULT profile in default location
# Refer to
# https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm#SDK_and_CLI_Configuration_File
# for more info


comp_id = os.environ.get('COMPARTMENT_OCID')
exa_id = os.environ.get('EXA_OCID')
profile = os.environ.get('PROFILE',"DEFAULT")

logging.getLogger('oci').setLevel(logging.DEBUG)

if comp_id is None:
    print(f"You didn't set COMPARTMENT_OCID into shell.")
    exit(1)

print(f"Using profile {profile}.")

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

#config["log_requests"] = True
database_management_client = DbManagementClient(config)
database_client = DatabaseClient(config)
usage_client = UsageapiClient(config)
monitoring_client = MonitoringClient(config)

# Main Flow - start with Infra OCID to get name
# ie ocid1.cloudexadatainfrastructure.oc1.iad.anuwcljthwcsg7aamltlbfnxf4lpqt5epmjfaquso6eaugpui4batr5wnktq = exacs_ash_ad3_npr1
# Comp OCID = ocid1.compartment.oc1..aaaaaaaabhc7rad3qzwlpls3pmwf62vmhdkbmx7dphvh2c2nnw5av3gu3hta

# Prod 1-1
# export COMPARTMENT_OCID=ocid1.compartment.oc1..aaaaaaaadnzdzsy7cwvndq2xmsbyrcslex6x7lvhzkdpk7sde6n4gpe7tspa
# export EXA_OCID=ocid1.cloudexadatainfrastructure.oc1.iad.anuwcljshwcsg7aa74rbufzcpzgqie3vx72pgd5nj52be6aasunzbcqx446q


# Get Infra
try:

    # Get Infra Detail
    rack = database_client.get_cloud_exadata_infrastructure(
        cloud_exadata_infrastructure_id=exa_id
    ).data
    #print(f"Rack Detail: Comp:{rack}", flush=True)
    print(f"Rack Detail: Comp:{rack.compute_count} Storage Count: {rack.storage_count} Total Storage(all ASM): {rack.total_storage_size_in_gbs} ID: {rack.id}", flush=True)

    # Apparantly not there yet
    # rack_unall = database_client.get_cloud_exadata_infrastructure_unallocated_resources(
    #     cloud_exadata_infrastructure_id=exa_id
    # ).data
    # print(f"Unall Detail: {rack_unall}",flush=True)

    # Cloud VM Cluster
    vm_cluster = database_client.list_cloud_vm_clusters(
        compartment_id=comp_id,
        cloud_exadata_infrastructure_id=rack.id
    ).data[0] # List of CloudVmClusterSummary - but only need first one of them

    # Try to get ExaCS Frame tag
    frame_tag = vm_cluster.defined_tags["Windstream_Tags"]["ExaCS_Frame"]
    # Print DB ID and Tags
    #print(f"VM Cluster Detail: {vm_cluster}", flush=True)
    print(f"VM Cluster Detail: {vm_cluster.cluster_name} Tags: {frame_tag} ID: {vm_cluster.id}", flush=True)


 
    # Total CPU and Storage
    rack_usable_storage = vm_cluster.storage_size_in_gbs * vm_cluster.data_storage_percentage * .01
    remaining_rack_usable_storage = rack_usable_storage
    print(f"Total OCPU: {vm_cluster.cpu_core_count} / Usable DATA Storage GB: {rack_usable_storage}",flush=True)

    # For each database on rack, get min_cpu_count and storage used
    # Cloud VM Cluster
    databases = database_client.list_databases(
        compartment_id=comp_id,
        system_id=vm_cluster.id,
        limit=100

    ).data # List of DatabaseSummary

    for i,db in enumerate(databases,start=1):
        # DB Details

        # Storage in use / Metric / 30 day average of average storage used
        # StorageUsed[1d]{resourceId_database = "DB OCID"}.mean()
        end_time = datetime.now()
        start_time = end_time - timedelta(days = 30)
        summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
            compartment_id=comp_id,
            summarize_metrics_data_details=SummarizeMetricsDataDetails(
                namespace="oci_database",
                query=f'StorageUsed[1d]{{resourceId_database ="{db.id}" }}.mean()',
                start_time=f"{start_time.isoformat()}Z",
                end_time=f"{end_time.isoformat()}Z",
                resolution="6h")
        ).data
        if summarize_metrics_data_response:

            # Loop to get an average
            sum = 0
            for dp in summarize_metrics_data_response[0].aggregated_datapoints:
                sum = sum + dp.value
            storage_used = sum / len(summarize_metrics_data_response[0].aggregated_datapoints)
            
            # Decrement Storage Remaining
            remaining_rack_usable_storage = remaining_rack_usable_storage - storage_used
            potential_percent_of_total = storage_used / (rack_usable_storage) * 100
            #print(f'{i}: Database {db.id} Storage Used: {summarize_metrics_data_response}', flush=True)
            print(f'{i}: Database {db.db_unique_name} Storage Used GB: {storage_used:.2f}, Percent: {potential_percent_of_total:.2f}', flush=True)
        else:
            print(f"No Metrics for DB: {db.db_unique_name}, Status: {db.lifecycle_state }")
        
        # Sleep a moment to give API some rest
        time.sleep(.5)
    # Print Remaining Storage
    print(f"Remaining Unused DATA Storage GB: {remaining_rack_usable_storage:.2f}")
except ServiceError as exc:
    print(f"Failed to get details for {exa_id}: {exc}")



