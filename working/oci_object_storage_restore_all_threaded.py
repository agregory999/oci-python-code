"""
Sample code for listing and restoring archived objects in an OCI bucket.
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
    parser = argparse.ArgumentParser(description='List and restore archived objects in an OCI bucket.')
    parser.add_argument('--bucket-name', required=True, help='Name of the OCI bucket')
    parser.add_argument('--compartment-id', required=True, help='OCID of the compartment')
    parser.add_argument('--profile', default='DEFAULT', help='OCI config profile name')
    parser.add_argument('--prefix', help='Prefix to filter objects (optional)')
    parser.add_argument('--restore-hours', type=int, default=24, help='Restore duration in hours (default: 24)')
    parser.add_argument('--max-workers', type=int, default=10, help='Max number of concurrent restore threads (default: 10)')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Print restore operations without executing (default: True)')
    parser.add_argument('--no-dry-run', dest='dry_run', action='store_false', help='Execute restore operations')
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

def restore_object(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                  bucket_name: str, object_name: str, restore_hours: int, dry_run: bool) -> None:
    """Restore a single archived object or print the operation for dry-run."""
    if dry_run:
        logger.info(f"DRY RUN: Would restore object {object_name} for {restore_hours} hours")
        return
    
    try:
        client.restore_objects(
            namespace_name=namespace,
            bucket_name=bucket_name,
            restore_objects_details=oci.object_storage.models.RestoreObjectsDetails(
                object_name=object_name,
                hours=restore_hours
            )
        )
        logger.info(f"Successfully requested restore for object: {object_name}")
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed to restore object {object_name}: {e}")

def update_progress(future: Future, total: int, counter: List[int], lock: threading.Lock) -> None:
    """Callback to update progress when a restore task completes."""
    with lock:
        counter[0] += 1
        logger.info(f"Restore progress: {counter[0]}/{total} operations completed")

def process_objects(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                   bucket_name: str, compartment_id: str, prefix: str, restore_hours: int, 
                   max_workers: int, dry_run: bool) -> None:
    """Stream objects using pagination and restore archived ones with progress tracking."""
    total_objects = 0
    archived_objects = 0
    counter = [0]  # Mutable counter for tracking completed restore tasks
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
                    logger.info(f"Pagination progress: Processed {total_objects} objects, found {archived_objects} archived")
                # logger.info(f"obj {obj.name} tier: {obj.storage_tier}/{obj.archival_state}")
                # Check if object is in Archive tier
                storage_tier = obj.storage_tier if hasattr(obj, 'storage_tier') else 'Standard'
                # Only do it if actually Archived.  If Restoring or Restored, skip it.
                if storage_tier == 'Archive' and obj.archival_state == 'Archived':
                    archived_objects += 1
                    # Submit restore task
                    future = executor.submit(
                        restore_object,
                        client,
                        namespace,
                        bucket_name,
                        obj.name,
                        restore_hours,
                        dry_run
                    )
                    future.add_done_callback(
                        lambda f: update_progress(f, archived_objects, counter, lock)
                    )
                    futures.append(future)
                
                # Trigger garbage collection every 1000 objects to reduce memory usage
                if total_objects % 1000 == 0:
                    gc.collect()
                
            # Wait for all restore operations to complete
            concurrent.futures.wait(futures)
        
        logger.info(f"Processed {total_objects} total objects, found {archived_objects} archived objects")
        logger.info(f"All {archived_objects} restore operations {'simulated' if dry_run else 'completed'}")
    
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed during object processing: {e}")
        raise

def main():
    """Main function to list and restore archived objects."""
    args = parse_arguments()
    
    try:
        # Initialize OCI client
        client = get_object_storage_client(args.profile)
        
        # Get namespace
        namespace = get_namespace(client)
        logger.info(f"Retrieved namespace: {namespace}")
        
        # Process objects with streaming and restore archived ones
        logger.info(f"Starting object processing for bucket {args.bucket_name}")
        process_objects(
            client,
            namespace,
            args.bucket_name,
            args.compartment_id,
            args.prefix,
            args.restore_hours,
            args.max_workers,
            args.dry_run
        )
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    main()