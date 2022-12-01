from oci import config
from oci.database_management import DbManagementClient
from oci.usage_api import UsageapiClient
from oci.database import DatabaseClient
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import os
from datetime import datetime, timedelta

# Create a default config using DEFAULT profile in default location
# Refer to
# https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm#SDK_and_CLI_Configuration_File
# for more info


comp_id = os.environ.get('COMPARTMENT_OCID')
exa_id = os.environ.get('EXA_OCID')
profile = os.environ.get('PROFILE',"DEFAULT")
if comp_id is None:
    print(f"You didn't set COMPARTMENT_OCID into shell.")
    exit(1)

print(f"Using profile {profile}.")

# Initialize service client with default config file
config = config.from_file(profile_name=profile)
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

    # Get Infra
    rack = database_client.get_cloud_exadata_infrastructure(
            cloud_exadata_infrastructure_id=exa_id
    ).data
    print(f"Rack Detail: Comp:{rack.compute_count} Storage Count: {rack.storage_count} ID: {rack.id}", flush=True)

    # Cloud VM Cluster
    vm_cluster = database_client.list_cloud_vm_clusters(
        compartment_id=comp_id,
        cloud_exadata_infrastructure_id=rack.id
    ).data[0] # List of CloudVmClusterSummary - but only need first one of them

    # Try to get ExaCS Frame tag
    frame_tag = vm_cluster.defined_tags["Windstream_Tags"]["ExaCS_Frame"]
    # Print DB ID and Tags
    print(f"VM Cluster Detail: {vm_cluster.name} ID: {vm_cluster.id} Tags: {frame_tag}", flush=True)

    # Rack Cost (take defined tag and run report)

    # Total CPU and Storage
    rack_usable_storage = vm_cluster.storage_size_in_gbs * vm_cluster.data_storage_percentage * .01
    print(f"Total OCPU: {vm_cluster.cpu_core_count} / Usable Storage GB: {rack_usable_storage}",flush=True)

    # For each database on rack, get min_cpu_count and storage used
    # Cloud VM Cluster
    databases = database_client.list_databases(
        compartment_id=comp_id,
        system_id=vm_cluster.id
    ).data # List of DatabaseSummary

    for i,db in enumerate(databases,start=1):
        # DB Details
        print(f"DB {i} Database: {db.db_name} ID: {db.id}")

        # # Grab CPU Min param
        # # Iterate Parameters (could fail) - (note the filter for parameters with "cpu" in name)
        # try:
        #     list_database_parameters_response = database_management_client.list_database_parameters(
        #         managed_database_id=db.id,
        #         source="CURRENT",
        #         name="min_cpu",
        #         #is_allowed_values_included=True,
        #         sort_by="NAME",
        #         sort_order="ASC"
        #     ).data

        #     for param in list_database_parameters_response.items:
        #         print(f"  Param {param.name}:{param.type}={param.value}", flush=True)
        # except ServiceError as exc:
        #     print(f"Failed to get params for {exa_id}: {exc.message}")

        # CPU in use
        try:
            database_metrics_response = database_management_client.get_database_home_metrics(
                managed_database_id=db.id,
                end_time=f'{datetime.now().isoformat(timespec="milliseconds")}Z',
                start_time=f'{(datetime.now() - timedelta(hours = 1)).isoformat(timespec="milliseconds")}Z'
            ).data # DatabaseHomeMetrics

            if database_metrics_response is None:
                print("  Empty DB Attributes - Please enable DB Management")
            # Do the work here    
            else:
                # # CPU
                # if database_metrics_response.database_instance_home_metrics is not None:
                #     # Not sure why there are more than 1
                #     for cccc in database_metrics_response.database_instance_home_metrics:
                #         print(f"  Instance # {cccc.instance_name} / CPU u: {cccc.cpu_utilization_aggregate_metrics.cpu_utilization}", flush=True)
                #         print(f"  Instance # {cccc.instance_name} / CPU s: {cccc.cpu_utilization_aggregate_metrics.cpu_statistics}", flush=True)
                # else:
                #     print (f"  No Instance Home Metrics exist for {exa_id} / {db.db_name}")

                # Now do Storage
                if database_metrics_response.database_home_metrics is not None and database_metrics_response.database_home_metrics.db_storage_aggregate_metrics is not None:
                    storage_allocated = database_metrics_response.database_home_metrics.db_storage_aggregate_metrics.storage_allocated.value
                    storage_used = database_metrics_response.database_home_metrics.db_storage_aggregate_metrics.storage_used.value
                    # Convert Rack storage to GB then divide
                    percent_of_total = storage_used / (rack_usable_storage) * 100
                    potential_percent_of_total = storage_allocated / (rack_usable_storage) * 100
                    print(f"  Storage In use / Allocated: {storage_used:.2f} / {storage_allocated:.2f} GB \
= Percent of Rack: {percent_of_total:.2f}% / Potential Percent of Rack: {potential_percent_of_total:.2f}%", flush=True)
                else:
                    print (f"  No Home Metrics exist for {exa_id} / {db.db_name}")
        except (ServiceError, AttributeError) as exc:
            print(f"  Failed to get storage for {exa_id}: {exc}")


except ServiceError as exc:
    print(f"Failed to get details for {exa_id}: {exc.message}")


# # List DBs managed by compartment
# list_managed_databases_response = database_management_client.list_managed_databases(
#     compartment_id=comp_id,
#     management_option='ADVANCED',
#     sort_by="NAME",
#     limit=100
# ).data

# for i,mdb in enumerate(list_managed_databases_response.items):

#     # Print DB Details
#     print(f"{i}: Database {mdb.name}:{mdb.id}:{mdb.deployment_type}:{mdb.database_sub_type}", flush=True)

#     if mdb.deployment_type == 'ONPREMISE':
#         print("not doing anything")
#         continue

#     # Assume Exadata here
#     try:
#         # Get Database from DB Client
#         database = database_client.get_database(
#             database_id=mdb.id
#         ).data

#         # Print DB Details
#         print(f"{i}: Database {mdb.name}:{database.vm_cluster_id}:{mdb.deployment_type}:{mdb.database_sub_type}", flush=True)

#         # For the VM Cluster, get the cost.  
#         # To do this, we need to get the VM Cluster in scope, get the ExaCS_Frame tag, then use that in a cost query
#         vm_cluster = database_client.get_cloud_vm_cluster(
#             cloud_vm_cluster_id=mdb.id
#         ).data

#         # Print DB Tags
#         print(f"{i}: Tags {vm_cluster.defined_tags}", flush=True)

#         # Get Storage From Metrics
#         # Metric Query will be 

#         end_time = datetime.now()
#         start_time = end_time - timedelta(days = 1)
#         summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
#             compartment_id=comp_id,
#             summarize_metrics_data_details=SummarizeMetricsDataDetails(
#                 namespace="oci_database",
#                 query=f'StorageUsed[1d]{{resourceId_database ="{mdb.id}" }}.mean()',
#                 start_time=f"{start_time.isoformat()}Z",
#                 end_time=f"{end_time.isoformat()}Z",
#                 resolution="1d")
#         ).data

#         # Print Storage Details
#         #print(f'{i}: Database {mdb.name} Storage Used: {summarize_metrics_data_response}', flush=True)
#         print(f'{i}: Database {mdb.name} Storage Used: {summarize_metrics_data_response[0].aggregated_datapoints[0].value}', flush=True)

#     except ServiceError as exc:
#         print(f"Failed to get storage for {mdb.name}: {exc.message}")


#     # # Iterate Parameters (could fail)
#     # try:
#     #     # Call in again to get parameters (note the filter for parameters with "cpu" in name)
#     #     list_database_parameters_response = database_management_client.list_database_parameters(
#     #         managed_database_id=mdb.id,
#     #         source="CURRENT",
#     #         name="min_cpu",
#     #         #is_allowed_values_included=True,
#     #         sort_by="NAME",
#     #         sort_order="ASC"
#     #     ).data

#     #     # Iterate Results
#     #     for param in list_database_parameters_response.items:
#     #             print(f"  Param {param.name}:{param.type}={param.value}", flush=True)
#     # except ServiceError as exc:
#     #     print(f"Failed to get parameters for {mdb.name}: {exc.message}")



# # Pseudocode
# # This would be at a daily scope - but would need to run daily to get breakdown because param changes and OCPU changes will occur and this history is not tracked per-se
# # Per (Exa Frame)
# #   Grab daily frame cost from usage API
# # Iterate DBs
# #   Code will not work if database is not managed
# #   Grab min_cpu_count
# #   Get Storage allocated
# #   Calculate cost by core and gig for this DB

# # exa_vmcluster_names = ["exacs_ash_vmc_ad2_prd5","exacs_ash_vmc_ad2_prd4"]
# # for vmc_name in exa_vmcluster_names:

# #     print(f"Getting details for Cluster {vmc_name}:")
# #     # Get details from VM Cluster and exa Infra
# #     database_client.get_exadata_infrastructure()
# #     database_client.get_vm_cluster()

# #     # Total cost for this rack (using cost-tracking) by day
# #     # Usage API - create a function
# #     usage_client.request_summarized_usages()
# #     rack_cost_month = 0

# #     # Iterate DBs for rack
# #     DatabaseClient

# #     # Storage
# #     # Pull metrics on storage used for this DB
# #     end_time = datetime.now()
# #     start_time = end_time - timedelta(days = 7)
# #     summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
# #         compartment_id=comp_id,
# #         summarize_metrics_data_details=SummarizeMetricsDataDetails(
# #             namespace="oci-database",
# #             query=f'StorageUsed[1d]{{resourceName ="{vmc_name}" }}.mean()',
# #             start_time=datetime.strptime(
# #                 start_time,
# #                 "%Y-%m-%dT%H:%M:%S.%fZ"),
# #             end_time=datetime.strptime(
# #                 end_time,
# #                 "%Y-%m-%dT%H:%M:%S.%fZ"),
# #             resolution="1d")
# #     ).data

# # # Get the data from response
# # print(summarize_metrics_data_response.data)

# #     # Figure out cost breakdown by resource allocation divided into total cost



