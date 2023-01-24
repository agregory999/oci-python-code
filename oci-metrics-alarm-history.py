from oci import config
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError

import argparse
from datetime import datetime, timedelta
import logging

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-c", "--compartmentocid", help="Metrics Compartment OCID", required=True)
parser.add_argument("-n", "--namespace", help="Metrics Namespace", required=True)
parser.add_argument("-r", "--resourcegroup", help="Resource Group")
parser.add_argument("-d", "--days", help="Days of data to analyze", default=3)
parser.add_argument("-q", "--query", help="Full metric query", required=True)
parser.add_argument("-t", "--threshold", help="Numeric threshold when crossed (will check value", required=True)

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
comp_ocid = args.compartmentocid
days = args.days
query = args.query
threshold = args.threshold
namespace = args.namespace
resource_group = args.resourcegroup

# If required, verbose
if verbose:
    print(f'Using verbose mode')
    logging.getLogger('oci').setLevel(logging.DEBUG)
print(f"Using profile {profile}.")
print(f'Using {days} days of data')
print(f'Using {comp_ocid} / {namespace} / {resource_group} / {query} / threshold {threshold}')

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Set up OCI clients
monitoring_client = MonitoringClient(config)

# Get Infra
try:
    # Start and end
    end_time = datetime.now()
    start_time = end_time - timedelta(days = int(days))
    
    # Define query
    query = SummarizeMetricsDataDetails(
            namespace=namespace,
            query=query,
            start_time=f"{start_time.isoformat()}Z",
            end_time=f"{end_time.isoformat()}Z"
            )
    if resource_group:
        query.resource_group = resource_group

    print(f"Metrics Query: {query}")

    # Query already created above - run it
    summarize_metrics_data_response = monitoring_client.summarize_metrics_data(
        compartment_id=comp_ocid,
        summarize_metrics_data_details=query
    ).data

    # Print count
    print(f"Metrics Result Size: {len(summarize_metrics_data_response)}")

    over = False
    for i,metric in enumerate(summarize_metrics_data_response):

        for dp in metric.aggregated_datapoints:

            if not over and dp.value > float(threshold):
                over = True
                print(f'\x1b[1;31mHost {metric.dimensions["resourceName"]} File System {metric.dimensions["fileSystemName"]} exceeded threshold ( t: {threshold} / val: {dp.value} ) at {dp.timestamp}\x1b[0m')
            elif over and dp.value <= float(threshold):
                over=False
                print(f'Host {metric.dimensions["resourceName"]} File System {metric.dimensions["fileSystemName"]} went below threshold ( t: {threshold} / val: {dp.value} ) at {dp.timestamp}')
        # End interating data points
        over = False
    # End loop    

except ServiceError as exc:
    print(f"Failed to get details: {exc}")

