from oci import config
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.exceptions import ServiceError
import math

import argparse
from datetime import datetime, timedelta
import logging

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-c", "--compartmentocid", help="Metrics Compartment OCID", required=True)
parser.add_argument("-d", "--days", help="Days of data to analyze ", default=3)
parser.add_argument("-q", "--query", help="Full metric query", required=True)
parser.add_argument("-n", "--namespace", help="Metrics Namespace", required=True)
parser.add_argument("-r", "--resourcegroup", help="Resource Group")
parser.add_argument("-dim", "--dimensions", help="Dimensions to Print", required=False, default=[], nargs='+')

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
comp_ocid = args.compartmentocid
days_to_average = args.days
query = args.query
namespace = args.namespace
resource_group = args.resourcegroup
dimensions = args.dimensions

# If required, verbose
if verbose:
    print(f'Using verbose mode')
    logging.getLogger('oci').setLevel(logging.DEBUG)
print(f"Using profile {profile}.")
print(f'Using {days_to_average} days of data')

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Set up OCI clients
monitoring_client = MonitoringClient(config)

# Get Infra
try:
    # Start and end
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days = int(days_to_average))

    # Namespace / Query
    # Example NS: oci_database
    # Example Query: TransactionCount[1d].sum()
    # Example command:
    # python3 ./oci-metric-query.py -c ocid1.compartment.oc1..xx.yy -n oci_database -q 'TransactionCount[1d].mean()' -d 30
    
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
    print(f"Metrics Result count: {len(summarize_metrics_data_response)}")
    print(f"Metrics Result: {summarize_metrics_data_response}")

    # Daily suumary
    #for i,metric in enumerate(summarize_metrics_data_response):
        #print(f'Database: {metric.dimensions["resourceName_database"]} / Data Points: {len(metric.aggregated_datapoints)}')
    #    print(f'Database: {metric.dimensions["resourceName_database"]} / Data Points: {metric.aggregated_datapoints}')

    # for i,metric in enumerate(summarize_metrics_data_response):
    #     to_print = False
    #     sum = 0
    #     for dp in metric.aggregated_datapoints:
    #         sum += dp.value
    #         if dp.value == 1:
    #             to_print = True
    #     average = sum / len(metric.aggregated_datapoints)
    #     #print (f"Average: {average} {type(average)}")
    #     #if math.isclose(average > threshold) :
    #     if average > threshold:
    #         print(f'{i}: Metric: {metric.name}', end=" ")
    #         for dim in dimensions:

    #             print(f'{dim}: {metric.dimensions[dim]}',end=" ")
    #         print(f'Average%: {average:.2f}')
        # Use colored text - red for >90 and yellow >75
        # if average > 90:
        #     print(f'\x1b[1;31m{i}: Host: {metric.dimensions["resourceName"]} Filesystem: {metric.dimensions["fileSystemName"]} Avg FS Usage%: {average:.2f} \x1b[0m')
        # elif average > 75:
        #     print(f'\x1b[1;33m{i}: Host: {metric.dimensions["resourceName"]} Filesystem: {metric.dimensions["fileSystemName"]} Avg FS Usage%: {average:.2f} \x1b[0m')
        # else:
        #     print(f'{i}: Host: {metric.dimensions["resourceName"]} Filesystem: {metric.dimensions["fileSystemName"]} Avg FS Usage%: {average:.2f}')

except ServiceError as exc:
    print(f"Failed to get details: {exc}")

