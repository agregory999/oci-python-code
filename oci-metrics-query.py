from oci import config
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import argparse, time
from datetime import datetime, timedelta
import logging
import csv
import os

# Create a default config using DEFAULT profile in default location
# Refer to
# https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm#SDK_and_CLI_Configuration_File
# for more info


# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-c", "--compartmentocid", help="Database Compartment OCID", required=True)
parser.add_argument("-d", "--daystoaverage", help="Days of data to analyze storage usage for", default=3)
parser.add_argument("-o", "--operation", help="(surround with quotes) == , !~ , =~ , !=", default="==")

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
comp_ocid = args.compartmentocid
days_to_average = args.daystoaverage
op = args.operation

# If required, verbose
if verbose:
    print(f'Using verbose mode')
    logging.getLogger('oci').setLevel(logging.DEBUG)
print(f"Using profile {profile}.")
print(f'Using {days_to_average} days of data to analyze storage')

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Set up OCI clients
monitoring_client = MonitoringClient(config)

# Get Infra
try:
    # Start and end
    end_time = datetime.now()
    start_time = end_time - timedelta(days = days_to_average)

    # Operation
    #fs_string = "/*ora002|/*ora003|/*ora004|/*ora005|/*ora006|/*ora007|/*ora008|/*ora009"
    fs_string = "*"
    
    # Define query
    query = SummarizeMetricsDataDetails(
            namespace="oracle_appmgmt",
            #query=f'FileSystemUtilization[6h]{{fileSystemName {op} "{fs_string}"}}.mean()',
            query=f'FileSystemUtilization[6h].mean()',
            start_time=f"{start_time.isoformat()}Z",
            end_time=f"{end_time.isoformat()}Z",
            resolution="12h")
    query.resource_group = "host"
    print(f"Metrics Query: {query}")

    # Query already created above - run it
    summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
        compartment_id=comp_ocid,
        summarize_metrics_data_details=query
    ).data

    # Print count
    print(f"Metrics Result: {len(summarize_metrics_data_response)}")

    threshold = 95

    for i,metric in enumerate(summarize_metrics_data_response):
        sum = 0
        for dp in metric.aggregated_datapoints:
            sum += dp.value
        average = sum / len(metric.aggregated_datapoints)
        
        # Use colored text - red for >90 and yellow >75
        if average > 90:
            print(f'\x1b[1;31m{i}: Host: {metric.dimensions["resourceName"]} Filesystem: {metric.dimensions["fileSystemName"]} Avg FS Usage%: {average:.2f} \x1b[0m')
        elif average > 75:
            print(f'\x1b[1;33m{i}: Host: {metric.dimensions["resourceName"]} Filesystem: {metric.dimensions["fileSystemName"]} Avg FS Usage%: {average:.2f} \x1b[0m')
        else:
            print(f'{i}: Host: {metric.dimensions["resourceName"]} Filesystem: {metric.dimensions["fileSystemName"]} Avg FS Usage%: {average:.2f}')

except ServiceError as exc:
    print(f"Failed to get details: {exc}")

