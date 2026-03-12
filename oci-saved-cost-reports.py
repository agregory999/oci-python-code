"""
oci-saved-cost-reports.py

Script to list all Saved Custom Tables (custom cost reports) for a tenancy and show JSON for a selected report.

Steps to implement:
- [ ] Analyze requirements and gather references
- [ ] Set up new script file (e.g., oci-list-saved-custom-tables.py)
- [ ] Implement function to list all Saved Custom Tables for tenancy
- [ ] Implement user selection logic for printed list
- [ ] Implement logic to fetch and display selected table’s JSON
- [ ] Test script functionality
- [ ] Verify formatting, usability, and documentation

Placeholder for implementation below.
"""
import oci
import json
import argparse
import sys
import logging
from oci.usage_api.models import QueryCollection, QueryDefinition, ReportQuery

def list_saved_queries(usage_api_client, compartment_id, logger):
    """
    Lists all Saved Queries for the tenancy.
    Returns: List of Query objects.
    """
    try:
        result = usage_api_client.list_queries(compartment_id=compartment_id)
        return result.data
    except Exception as e:
        logger.error(f"Error retrieving saved queries: {e}")
        return []

def create_usage_api_client_from_args(args, logger):
    # if any required param is missing, try to load from config, else error
    config = {}
    # If user, tenancy, fingerprint, key_file, region are provided, build config from args
    if (
        args.user and args.tenancy and args.fingerprint
        and args.key_file and args.region
    ):
        logger.info("Using OCI config from CLI arguments.")
        config = {
            "user": args.user,
            "tenancy": args.tenancy,
            "fingerprint": args.fingerprint,
            "key_file": args.key_file,
            "region": args.region,
        }
        try:
            return oci.usage_api.UsageapiClient(config), args.compartment_id
        except Exception as e:
            logger.error(f"Failed to create UsageApiClient with CLI args: {e}")
            sys.exit(1)
    else:
        # Fall back to config file and profile (default: DEFAULT)
        profile = args.profile or "DEFAULT"
        try:
            config = oci.config.from_file(profile_name=profile)
            compartment_id = args.compartment_id or config.get("tenancy")
            if not compartment_id:
                raise Exception("Missing compartment_id argument or tenancy OCID in config.")
            logger.info(f"Using OCI config file with profile: {profile}")
            return oci.usage_api.UsageapiClient(config), compartment_id
        except Exception as e:
            logger.error("Failed to load OCI configuration or create client.")
            logger.error(f"Error: {e}")
            logger.error("You must set all required OCI parameters via CLI or config file.")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="List all OCI Saved Custom Cost Reports and show JSON for a selected report."
    )
    parser.add_argument("--profile", help="OCI config profile (default: DEFAULT)")
    parser.add_argument("--compartment-id", help="Compartment OCID for listing reports (defaults to tenancy from config/profile)")
    parser.add_argument("--user", help="User OCID")
    parser.add_argument("--tenancy", help="Tenancy OCID")
    parser.add_argument("--fingerprint", help="API key fingerprint")
    parser.add_argument("--key-file", help="Path to private API key file")
    parser.add_argument("--region", help="OCI region (e.g. us-ashburn-1)")
    parser.add_argument("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("oci-saved-cost-reports")

    usage_api_client, compartment_id = create_usage_api_client_from_args(args, logger)

    # List Saved Queries
    queries:QueryCollection = list_saved_queries(usage_api_client, compartment_id, logger)
    if not queries:
        logger.warning("No saved queries found.")
        return
    logger.info(f"Saved Queries: {len(queries.items)} found.")
    for idx, query in enumerate(queries.items, start=1):
        query_def:QueryDefinition = query.query_definition
        logger.info(f"{idx}. {query_def.display_name} (OCID: {query.id})")

    # Prompt user to choose a query by index
    while True:
        try:
            choice = int(input("\nEnter the number of the query to show its JSON (0 to exit): "))
            if choice == 0:
                logger.info("Exiting.")
                break
            if 1 <= choice <= len(queries.items):
                selected_query = queries.items[choice - 1]
                query_def:QueryDefinition = selected_query.query_definition
                logger.info(f"JSON for query: {query_def} ")
                # report_query:ReportQuery = query_def.report_query
                # logger.info(f"Report Query: {report_query}")
                break
            else:
                logger.warning(f"Invalid selection. Choose 1-{len(queries.items)} or 0 to exit.")
        except ValueError:
            logger.warning("Invalid input. Enter a number.")

if __name__ == "__main__":
    main()
