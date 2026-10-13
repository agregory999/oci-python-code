import asyncio
import logging
import os
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

# Define the list_instances function
async def list_instances(compartment_id: str) -> List[Dict[str, Any]]:
    """
    List all compute instances in the specified OCI compartment.
    Args:
        compartment_id: OCI compartment ID (e.g., ocid1.compartment.oc1..xxxx)
    Returns:
        List of dictionaries containing instance details (ID, display name, lifecycle state)
    """
    logger.info(f"Listing instances in compartment: {compartment_id}")
    if not compartment_id:
        raise ValueError("compartment_id is required")
    try:
        instances = compute_client.list_instances(compartment_id=compartment_id).data
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

# JSON-RPC dispatcher for MCP
async def dispatch(request: dict) -> dict:
    """
    Handle JSON-RPC requests for MCP.
    """
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")

    if method == "list_instances":
        try:
            result = await list_instances(params.get("compartment_id", ""))
            return {"jsonrpc": "2.0", "result": result, "id": request_id}
        except Exception as e:
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": request_id}
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method {method} not found"},
            "id": request_id
        }

# Main function to run the MCP server
async def main():
    logger.info("Starting OCI MCP server")
    await run_server(dispatch, name="oci-mcp-server")

if __name__ == "__main__":
    asyncio.run(main())