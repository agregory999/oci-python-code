#!/usr/bin/env python3
"""
Oracle Cloud Infrastructure (OCI) Compute Instance Group Manager
FastMCP Server for managing groups of compute instances
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

import oci
from fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("OCI Instance Group Manager")

# Global cache for OCI clients and configs by profile
client_cache: Dict[str, oci.core.ComputeClient] = {}
config_cache: Dict[str, Dict] = {}

def get_oci_client(profile_name: str = "DEFAULT") -> Tuple[oci.core.ComputeClient, Dict]:
    """Get OCI client and config for a specific profile, with caching"""
    if profile_name in client_cache:
        return client_cache[profile_name], config_cache[profile_name]
    
    try:
        # Load OCI config from default location or environment
        config_file = os.getenv('OCI_CONFIG_FILE', '~/.oci/config')
        
        config = oci.config.from_file(config_file, profile_name)
        compute_client = oci.core.ComputeClient(config)
        
        # Cache the client and config
        client_cache[profile_name] = compute_client
        config_cache[profile_name] = config
        
        logger.info(f"OCI configuration loaded successfully for profile: {profile_name}")
        return compute_client, config
    except Exception as e:
        logger.error(f"Failed to load OCI configuration for profile {profile_name}: {e}")
        raise

def load_instance_groups(groups_file: str = "instance_groups.json") -> Dict[str, Dict]:
    """Load instance groups from JSON file"""
    try:
        groups_path = Path(groups_file)
        if not groups_path.exists():
            # Create default groups file if it doesn't exist
            default_groups = {
                "web_servers": {
                    "profile": "DEFAULT",
                    "instances": [
                        "ocid1.instance.oc1.region.example1",
                        "ocid1.instance.oc1.region.example2"
                    ]
                },
                "database_servers": {
                    "profile": "PROD",
                    "instances": [
                        "ocid1.instance.oc1.region.example3"
                    ]
                },
                "development": {
                    "profile": "DEV",
                    "instances": [
                        "ocid1.instance.oc1.region.example4",
                        "ocid1.instance.oc1.region.example5"
                    ]
                }
            }
            with open(groups_file, 'w') as f:
                json.dump(default_groups, f, indent=2)
            logger.info(f"Created default instance groups file: {groups_file}")
            return default_groups
        
        with open(groups_file, 'r') as f:
            groups = json.load(f)
        
        # Validate and migrate old format if needed
        validated_groups = {}
        for group_name, group_data in groups.items():
            if isinstance(group_data, list):
                # Old format - migrate to new format with default profile
                logger.warning(f"Migrating group '{group_name}' from old format to new format")
                validated_groups[group_name] = {
                    "profile": "DEFAULT",
                    "instances": group_data
                }
            elif isinstance(group_data, dict) and "instances" in group_data:
                # New format
                profile = group_data.get("profile", "DEFAULT")
                validated_groups[group_name] = {
                    "profile": profile,
                    "instances": group_data["instances"]
                }
            else:
                logger.error(f"Invalid format for group '{group_name}', skipping")
                continue
        
        # Save migrated format if changes were made
        if validated_groups != groups:
            with open(groups_file, 'w') as f:
                json.dump(validated_groups, f, indent=2)
            logger.info(f"Migrated and saved instance groups file: {groups_file}")
        
        logger.info(f"Loaded {len(validated_groups)} instance groups from {groups_file}")
        return validated_groups
    except Exception as e:
        logger.error(f"Failed to load instance groups: {e}")
        return {}

def get_instance_details(instance_id: str, profile_name: str = "DEFAULT") -> Dict[str, Any]:
    """Get details for a single instance using specified profile"""
    try:
        compute_client, _ = get_oci_client(profile_name)
        response = compute_client.get_instance(instance_id)
        instance = response.data
        return {
            "id": instance.id,
            "display_name": instance.display_name,
            "lifecycle_state": instance.lifecycle_state,
            "availability_domain": instance.availability_domain,
            "shape": instance.shape,
            "time_created": str(instance.time_created),
            "profile": profile_name
        }
    except Exception as e:
        logger.error(f"Failed to get instance details for {instance_id} using profile {profile_name}: {e}")
        return {
            "id": instance_id,
            "error": str(e),
            "lifecycle_state": "UNKNOWN",
            "profile": profile_name
        }

def start_instance(instance_id: str, profile_name: str = "DEFAULT") -> Dict[str, Any]:
    """Start a single instance using specified profile"""
    try:
        compute_client, _ = get_oci_client(profile_name)
        compute_client.instance_action(instance_id, "START")
        logger.info(f"Started instance: {instance_id} using profile: {profile_name}")
        return {"id": instance_id, "action": "START", "status": "SUCCESS", "profile": profile_name}
    except Exception as e:
        logger.error(f"Failed to start instance {instance_id} using profile {profile_name}: {e}")
        return {"id": instance_id, "action": "START", "status": "ERROR", "error": str(e), "profile": profile_name}

def stop_instance(instance_id: str, profile_name: str = "DEFAULT") -> Dict[str, Any]:
    """Stop a single instance using specified profile"""
    try:
        compute_client, _ = get_oci_client(profile_name)
        compute_client.instance_action(instance_id, "STOP")
        logger.info(f"Stopped instance: {instance_id} using profile: {profile_name}")
        return {"id": instance_id, "action": "STOP", "status": "SUCCESS", "profile": profile_name}
    except Exception as e:
        logger.error(f"Failed to stop instance {instance_id} using profile {profile_name}: {e}")
        return {"id": instance_id, "action": "STOP", "status": "ERROR", "error": str(e), "profile": profile_name}

@mcp.tool()
def list_instance_groups() -> str:
    """List all available instance groups and their member instances"""
    groups = load_instance_groups()
    
    result = []
    result.append("Available Instance Groups:")
    result.append("=" * 30)
    
    for group_name, group_data in groups.items():
        profile = group_data.get("profile", "DEFAULT")
        instance_ids = group_data.get("instances", [])
        result.append(f"\nGroup: {group_name}")
        result.append(f"Profile: {profile}")
        result.append(f"Instances ({len(instance_ids)}):")
        for instance_id in instance_ids:
            result.append(f"  - {instance_id}")
    
    return "\n".join(result)

@mcp.tool()
def get_group_status(group_name: str) -> str:
    """Get the current status of all instances in a group"""
    groups = load_instance_groups()
    
    if group_name not in groups:
        available_groups = ", ".join(groups.keys())
        return f"Group '{group_name}' not found. Available groups: {available_groups}"
    
    group_data = groups[group_name]
    profile = group_data.get("profile", "DEFAULT")
    instance_ids = group_data.get("instances", [])
    
    result = []
    result.append(f"Status for group '{group_name}' (Profile: {profile}):")
    result.append("=" * 50)
    
    for instance_id in instance_ids:
        details = get_instance_details(instance_id, profile)
        if "error" in details:
            result.append(f"\n❌ {instance_id}")
            result.append(f"   Error: {details['error']}")
            result.append(f"   Profile: {profile}")
        else:
            status_emoji = "🟢" if details["lifecycle_state"] == "RUNNING" else "🔴" if details["lifecycle_state"] == "STOPPED" else "🟡"
            result.append(f"\n{status_emoji} {details['display_name']} ({instance_id[:20]}...)")
            result.append(f"   State: {details['lifecycle_state']}")
            result.append(f"   Shape: {details['shape']}")
            result.append(f"   AD: {details['availability_domain']}")
            result.append(f"   Profile: {profile}")
    
    return "\n".join(result)

@mcp.tool()
def start_group(group_name: str) -> str:
    """Start all instances in a group"""
    groups = load_instance_groups()
    
    if group_name not in groups:
        available_groups = ", ".join(groups.keys())
        return f"Group '{group_name}' not found. Available groups: {available_groups}"
    
    group_data = groups[group_name]
    profile = group_data.get("profile", "DEFAULT")
    instance_ids = group_data.get("instances", [])
    
    result = []
    result.append(f"Starting group '{group_name}' ({len(instance_ids)} instances, Profile: {profile}):")
    result.append("=" * 60)
    
    success_count = 0
    for instance_id in instance_ids:
        action_result = start_instance(instance_id, profile)
        if action_result["status"] == "SUCCESS":
            result.append(f"✅ Started {instance_id}")
            success_count += 1
        else:
            result.append(f"❌ Failed to start {instance_id}: {action_result.get('error', 'Unknown error')}")
    
    result.append(f"\nSummary: {success_count}/{len(instance_ids)} instances started successfully")
    return "\n".join(result)

@mcp.tool()
def stop_group(group_name: str) -> str:
    """Stop all instances in a group"""
    groups = load_instance_groups()
    
    if group_name not in groups:
        available_groups = ", ".join(groups.keys())
        return f"Group '{group_name}' not found. Available groups: {available_groups}"
    
    group_data = groups[group_name]
    profile = group_data.get("profile", "DEFAULT")
    instance_ids = group_data.get("instances", [])
    
    result = []
    result.append(f"Stopping group '{group_name}' ({len(instance_ids)} instances, Profile: {profile}):")
    result.append("=" * 60)
    
    success_count = 0
    for instance_id in instance_ids:
        action_result = stop_instance(instance_id, profile)
        if action_result["status"] == "SUCCESS":
            result.append(f"✅ Stopped {instance_id}")
            success_count += 1
        else:
            result.append(f"❌ Failed to stop {instance_id}: {action_result.get('error', 'Unknown error')}")
    
    result.append(f"\nSummary: {success_count}/{len(instance_ids)} instances stopped successfully")
    return "\n".join(result)

@mcp.tool()
def add_instance_to_group(group_name: str, instance_id: str, profile_name: str = None, groups_file: str = "instance_groups.json") -> str:
    """Add an instance to a group"""
    groups = load_instance_groups(groups_file)
    
    if group_name not in groups:
        # Create new group if it doesn't exist
        if profile_name is None:
            return f"Group '{group_name}' doesn't exist. Please specify a profile_name to create a new group."
        groups[group_name] = {"profile": profile_name, "instances": []}
    
    group_data = groups[group_name]
    current_profile = group_data.get("profile", "DEFAULT")
    instance_list = group_data.get("instances", [])
    
    # Use group's profile if no profile specified
    if profile_name is None:
        profile_name = current_profile
    elif profile_name != current_profile:
        return f"Profile mismatch: Group '{group_name}' uses profile '{current_profile}', but you specified '{profile_name}'"
    
    if instance_id in instance_list:
        return f"Instance {instance_id} is already in group '{group_name}'"
    
    # Validate instance exists
    details = get_instance_details(instance_id, profile_name)
    if "error" in details:
        return f"Cannot add instance {instance_id}: {details['error']}"
    
    instance_list.append(instance_id)
    groups[group_name]["instances"] = instance_list
    
    try:
        with open(groups_file, 'w') as f:
            json.dump(groups, f, indent=2)
        return f"✅ Added instance {instance_id} ({details['display_name']}) to group '{group_name}' (Profile: {profile_name})"
    except Exception as e:
        return f"❌ Failed to save groups file: {e}"

@mcp.tool()
def remove_instance_from_group(group_name: str, instance_id: str, groups_file: str = "instance_groups.json") -> str:
    """Remove an instance from a group"""
    groups = load_instance_groups(groups_file)
    
    if group_name not in groups:
        return f"Group '{group_name}' not found"
    
    group_data = groups[group_name]
    instance_list = group_data.get("instances", [])
    
    if instance_id not in instance_list:
        return f"Instance {instance_id} is not in group '{group_name}'"
    
    instance_list.remove(instance_id)
    
    # Remove group if empty
    if not instance_list:
        del groups[group_name]
        action_msg = f"✅ Removed instance {instance_id} from group '{group_name}' and deleted empty group"
    else:
        groups[group_name]["instances"] = instance_list
        action_msg = f"✅ Removed instance {instance_id} from group '{group_name}'"
    
    try:
        with open(groups_file, 'w') as f:
            json.dump(groups, f, indent=2)
        return action_msg
    except Exception as e:
        return f"❌ Failed to save groups file: {e}"

def main():
    """Main function to run the FastMCP server"""
    try:
        # Ensure instance groups file exists
        load_instance_groups()
        
        # Run the MCP server
        mcp.run(transport="streamable-http", host="0.0.0.0", port=9000)
        
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        raise

if __name__ == "__main__":
    main()