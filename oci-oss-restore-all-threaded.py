"""
Sample code for listing and restoring archived objects in an OCI bucket.
This is not an official Oracle product and is provided as-is without any warranty.
Use at your own risk and ensure proper testing before use in production environments.
This sample uses OCI Official SDK for Python with additional Python libraries.

Author: Andrew Gregory, Oracle 

Installation: 
Python 3.9+
pip install oci

Usage:
python oci-oss-restore-all-threaded.py --bucket-name <bucket_name> --compartment-id <compartment_id> [--profile <profile_name>] 
[--restore-hours <hours>] [--max-workers <num_threads>] [--dry-run | --no-dry-run]

Example (Dry run):
python oci-oss-restore-all-threaded.py --bucket-name my_bucket --compartment-id ocid1.compartment.oc1..aaaaaaaaxxxxx --dry-run

Example (Execute restore):
python oci-oss-restore-all-threaded.py --bucket-name my_bucket --compartment-id ocid1.compartment.oc1..aaaaaaaaxxxxx --no-dry-run --restore-hours 48 --max-workers 8

Threading and Progress Tracking:
- Uses ThreadPoolExecutor for concurrent restore operations.  8 is the practical max for most environments.
- Progress is logged every 1000 objects during listing and after each restore operation completes.
"""

import oci
import argparse
import concurrent.futures
import logging
import threading
from typing import List, Dict
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

def list_objects(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                 bucket_name: str, compartment_id: str) -> List[Dict]:
    """List all objects in the bucket using oci.pagination with progress tracking."""
    objects = []
    total_objects = 0
    
    try:
        # Use generator-based pagination for progress tracking
        paginator = oci.pagination.list_call_get_all_results_generator(
            client.list_objects,
            'record',  # Yield individual records
            namespace_name=namespace,
            bucket_name=bucket_name,
            fields="name,size,storageTier"
        )
        
        for obj in paginator:
            objects.append({
                'name': obj.name,
                'storage_tier': obj.storage_tier if hasattr(obj, 'storage_tier') else 'Standard'
            })
            total_objects += 1
            # Log progress every 1000 objects (adjustable threshold)
            if total_objects % 1000 == 0:
                logger.info(f"Pagination progress: Fetched {total_objects} objects")
                
        logger.info(f"Total objects found in bucket {bucket_name}: {total_objects}")
        return objects
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed to list objects: {e}")
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

def main():
    """Main function to list and restore archived objects."""
    args = parse_arguments()
    
    try:
        # Initialize OCI client
        client = get_object_storage_client(args.profile)
        
        # Get namespace
        namespace = get_namespace(client)
        logger.info(f"Retrieved namespace: {namespace}")
        
        # List all objects with progress tracking
        logger.info(f"Starting object listing for bucket {args.bucket_name}")
        objects = list_objects(client, namespace, args.bucket_name, args.compartment_id)
        
        # Filter archived objects
        archived_objects = [obj for obj in objects if obj['storage_tier'] == 'Archive']
        total_archived = len(archived_objects)
        logger.info(f"Found {total_archived} archived objects")
        
        # Restore archived objects using thread pool
        if archived_objects:
            counter = [0]  # Mutable counter for tracking completed tasks
            lock = threading.Lock()  # Lock for thread-safe counter updates
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                futures = [
                    executor.submit(
                        restore_object,
                        client,
                        namespace,
                        args.bucket_name,
                        obj['name'],
                        args.restore_hours,
                        args.dry_run
                    )
                    for obj in archived_objects
                ]
                
                # Add callback for progress updates
                for future in futures:
                    future.add_done_callback(
                        lambda f: update_progress(f, total_archived, counter, lock)
                    )
                
                # Wait for all restore operations to complete
                concurrent.futures.wait(futures)
                
            logger.info(f"All {total_archived} restore operations {'simulated' if args.dry_run else 'completed'}")
        else:
            logger.info("No archived objects found to restore")
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    main()