"""
Sample code for changing the storage tier of restored Archive objects to InfrequentAccess in an OCI bucket.
This is not an official Oracle product and is provided as-is without any warranty.
Use at your own risk and ensure proper testing before use in production environments.
"""

import oci
import argparse
import logging
import threading
import concurrent.futures
import gc
from typing import Dict, List
from concurrent.futures import Future

# Configure logging with thread name
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Change storage tier of restored Archive objects to InfrequentAccess in an OCI bucket.')
    parser.add_argument('--bucket-name', required=True, help='Name of the OCI bucket')
    parser.add_argument('--compartment-id', required=True, help='OCID of the compartment')
    parser.add_argument('--prefix', help='Prefix to filter objects (optional)')
    parser.add_argument('--profile', default='DEFAULT', help='OCI config profile name')
    parser.add_argument('--max-workers', type=int, default=10, help='Max number of concurrent tier change threads (default: 10)')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Print tier change operations without executing (default: True)')
    parser.add_argument('--no-dry-run', dest='dry_run', action='store_false', help='Execute tier change operations')
    return parser.parse_args()

def get_object_storage_client(profile: str) -> oci.object_storage.ObjectStorageClient:
    """Initialize and return OCI Object Storage client."""
    try:
        config = oci.config.from_file(profile_name=profile)
        return oci.object_storage.ObjectStorageClient(config)
    except oci.exceptions.ConfigFileNotFound as e:
        logger.error(f"Failed to load OCI config: {e}")
        raise

def get_namespace(client: oci.object_storage.ObjectStorageClient) -> str:
    """Retrieve the object storage namespace."""
    try:
        response = client.get_namespace()
        return response.data
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed to get namespace: {e}")
        raise

def change_object_tier(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                      bucket_name: str, object_name: str, dry_run: bool) -> None:
    """Change the storage tier of a single object to InfrequentAccess or print for dry-run."""
    if dry_run:
        logger.info(f"DRY RUN: Would change tier of object {object_name} to InfrequentAccess")
        return
    
    try:
        client.update_object_storage_tier(
            namespace_name=namespace,
            bucket_name=bucket_name,
            update_object_storage_tier_details=oci.object_storage.models.UpdateObjectStorageTierDetails(
                object_name=object_name,
                storage_tier='InfrequentAccess'
            )
        )
        logger.info(f"Successfully changed tier for object: {object_name} to InfrequentAccess")
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed to change tier for object {object_name}: {e}")

def update_progress(future: Future, total: int, counter: List[int], lock: threading.Lock) -> None:
    """Callback to update progress when a tier change task completes."""
    with lock:
        counter[0] += 1
        logger.info(f"Tier change progress: {counter[0]}/{total} operations completed")

def process_objects(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                   bucket_name: str, compartment_id: str, prefix: str, 
                   max_workers: int, dry_run: bool) -> None:
    """Stream objects using pagination and change tier for restored Archive objects."""
    total_objects = 0
    restored_objects = 0
    counter = [0]  # Mutable counter for tracking completed tier change tasks
    lock = threading.Lock()  # Lock for thread-safe counter updates
    futures = []
    
    try:
        # Use generator-based pagination for streaming objects
        paginator = oci.pagination.list_call_get_all_results_generator(
            client.list_objects,
            'record',  # Yield individual records
            namespace_name=namespace,
            bucket_name=bucket_name,
            prefix=prefix if prefix else None,
            fields="name,storageTier,archivalState"
        )
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for obj in paginator:
                total_objects += 1
                # Log pagination progress every 1000 objects
                if total_objects % 1000 == 0:
                    logger.info(f"Pagination progress: Processed {total_objects} objects, found {restored_objects} restored Archive objects")
                
                # Check if object is in Archive tier and Restored state
                storage_tier = obj.storage_tier if hasattr(obj, 'storage_tier') else 'Standard'
                if storage_tier == 'Archive' and obj.archival_state == 'Restored':
                    restored_objects += 1
                    # Submit tier change task
                    future = executor.submit(
                        change_object_tier,
                        client,
                        namespace,
                        bucket_name,
                        obj.name,
                        dry_run
                    )
                    future.add_done_callback(
                        lambda f: update_progress(f, restored_objects, counter, lock)
                    )
                    futures.append(future)
                
                # Trigger garbage collection every 1000 objects to reduce memory usage
                if total_objects % 1000 == 0:
                    gc.collect()
                
            # Wait for all tier change operations to complete
            concurrent.futures.wait(futures)
        
        logger.info(f"Processed {total_objects} total objects, found {restored_objects} restored Archive objects")
        logger.info(f"All {restored_objects} tier change operations {'simulated' if dry_run else 'completed'}")
    
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed during object processing: {e}")
        raise

def main():
    """Main function to list and change storage tier of restored Archive objects."""
    args = parse_arguments()
    
    try:
        # Initialize OCI client
        client = get_object_storage_client(args.profile)
        
        # Get namespace
        namespace = get_namespace(client)
        logger.info(f"Retrieved namespace: {namespace}")
        
        # Process objects with streaming and change tier for restored Archive objects
        logger.info(f"Starting object processing for bucket {args.bucket_name}" + 
                    (f" with prefix {args.prefix}" if args.prefix else ""))
        process_objects(
            client,
            namespace,
            args.bucket_name,
            args.compartment_id,
            args.prefix,
            args.max_workers,
            args.dry_run
        )
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    main()