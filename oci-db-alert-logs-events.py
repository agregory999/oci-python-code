import oci
from datetime import datetime
import argparse   # Argument Parsing
import logging    # Python Logging
import uuid

# OCI Imports
from oci.loggingingestion import LoggingClient
from oci.loggingingestion.models import LogEntry, LogEntryBatch

# Only if called in Main
if __name__ == "__main__":
    # Arguments

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    #parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("-m", "--manageddb", help="Managed DB", nargs='+', required=True)
    #parser.add_argument("-n", "--namedcredential", help="Output Markdown (directory)")
    #parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose  # Boolean
    profile = args.profile  # String
    use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
    managed_ocids = args.manageddb 

    # Connect to tenancy
    config = oci.config.from_file()
    database_management_client = oci.database_management.DiagnosabilityClient(config)
    logging_client = LoggingClient(config)

    # Pull DB Alert Logs via DB Management
    for m_id in managed_ocids:
        print(f"Pulling logs for {m_id} for today")
        list_alert_logs_response = database_management_client.list_alert_logs(
            managed_database_id=m_id,
            time_greater_than_or_equal_to=datetime.strptime(
                "2024-05-08T00:00Z",
                "%Y-%m-%dT%H:%MZ"),
            time_less_than_or_equal_to=datetime.strptime(
                "2024-05-08T23:59Z",
                "%Y-%m-%dT%H:%MZ"),
            level_filter="ALL",
            #type_filter="TRACE",
            #log_search_text="EXAMPLE-logSearchText-Value",
            #is_regular_expression=True,
            sort_by="TIMESTAMP",
            sort_order="ASC",
            #page="EXAMPLE-page-Value",
            #limit=193,
            opc_named_credential_id="ocid1.dbmgmtnamedcredential.oc1.iad.amaaaaaaytsgwayahv4j5yh34d3mg6rfk5sf3ynlkh7iysqh3annplsqoqia")

    # Get the data from response
    print(list_alert_logs_response.data)

    # Process Response into Logs
    entries = []
    for entry in list_alert_logs_response.data:
         entries.append(LogEntry(id=str(uuid.uuid1()),
                                data=f"OCI"))
    log_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.now(datetime.timezone.utc),
                                source="oci-policy-analysis",
                                type="regular-statement",
                                entries=entries)
