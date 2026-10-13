import asyncio
import os
import logging
from typing import List, Dict, Any
from mcp.cli import run_server
import oci
from oci.config import from_file
from dotenv import load_dotenv

# Set up Python logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OCI-MCP-Server")

# Load environment variables from .env file (optional)
load_dotenv()

# Load OCI configuration from ~/.oci/config
try:
    oci_config = from_file()
except Exception as e:
    logger.error(f"Failed to load OCI config: {str(e)}")
    raise Exception(f"Failed to load OCI config: {str(e)}")

# Initialize OCI Compute Client
compute_client = oci.core.ComputeClient(oci_config)

# Define MCP tool to list compute instances
@tool
async def list_instances(compartment_id: str) -> List[Dict[str, Any]]:
    """
    List all compute instances in the specified OCI compartment.
    Args:
        compartment_id: OCI compartment ID (e.g., ocid1.compartment.oc1..xxxx)
    Returns:
        List of dictionaries containing instance details (ID, display name, lifecycle state)
    """
    logger.info(f"Listing instances in compartment: {compartment_id}")
    try:
        # Call OCI API to list instances
        instances = compute_client.list_instances(compartment_id=compartment_id).data
        # Format response
        result = [
            {
                "id": instance.id,
                "display_name": instance.display_name,
                "lifecycle_state": instance.lifecycle_state
            }
            for instance in instances
        ]
        logger.info(f"Found {len(result)} instances")
        return result
    except oci.exceptions.ServiceError as e:
        logger.error(f"OCI API error: {e.message}")
        raise Exception(f"Failed to list instances: {e.message}")

# Main function to run the MCP server
async def main():
    server = Server(name="oci-mcp-server")
    server.register_tool(list_instances)
    logger.info("Starting OCI MCP server")
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())