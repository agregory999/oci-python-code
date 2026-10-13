import os
import asyncio
from typing import List, Dict, Any
from mcp import Se
#from mcp.fastmcp import FastMCP, Context
from fastmcp import FastMCP
import oci
from oci.config import from_file
from oci.core import ComputeClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize MCP server
mcp = FastMCP("OCI-MCP-Server")

# Load OCI configuration from ~/.oci/config
try:
    oci_config = from_file()
except Exception as e:
    raise Exception(f"Failed to load OCI config: {str(e)}")

# Initialize OCI Compute Client
compute_client = ComputeClient(oci_config)

# Tool to list compute instances in a compartment
@mcp.tool()
async def list_instances(compartment_id: str, ctx: Context) -> List[Dict[str, Any]]:
    """
    List all compute instances in the specified OCI compartment.
    Args:
        compartment_id: OCI compartment ID (e.g., ocid1.compartment.oc1..xxxx)
    Returns:
        List of dictionaries containing instance details (ID, display name, lifecycle state)
    """
    ctx.info(f"Listing instances in compartment: {compartment_id}")
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
        ctx.info(f"Found {len(result)} instances")
        return result
    except oci.exceptions.ServiceError as e:
        ctx.error(f"OCI API error: {e.message}")
        raise Exception(f"Failed to list instances: {e.message}")

# Tool to launch a new compute instance
@mcp.tool()
async def launch_instance(
    compartment_id: str,
    display_name: str,
    image_id: str,
    shape: str,
    subnet_id: str,
    ctx: Context
) -> Dict[str, Any]:
    """
    Launch a new compute instance in OCI.
    Args:
        compartment_id: OCI compartment ID
        display_name: Name for the new instance
        image_id: OCI image ID (e.g., Oracle Linux image)
        shape: Instance shape (e.g., VM.Standard.E2.1.Micro)
        subnet_id: Subnet ID for the instance
    Returns:
        Dictionary with instance ID and status
    """
    ctx.info(f"Launching instance '{display_name}' in compartment {compartment_id}")
    try:
        # Define instance configuration
        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=compartment_id,
            display_name=display_name,
            image_id=image_id,
            shape=shape,
            subnet_id=subnet_id,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=1, memory_in_gbs=1
            )
        )
        # Launch instance
        response = compute_client.launch_instance(launch_details).data
        ctx.info(f"Instance launched: {response.id}")
        return {
            "instance_id": response.id,
            "lifecycle_state": response.lifecycle_state
        }
    except oci.exceptions.ServiceError as e:
        ctx.error(f"OCI API error: {e.message}")
        raise Exception(f"Failed to launch instance: {e.message}")

# Main function to run the server
async def main():
    server = Server("oci-mcp-server")
    await server.serve(mcp)

if __name__ == "__main__":
    asyncio.run(main())