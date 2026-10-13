"""
Sample code for creating an archive-mode bucket in OCI and uploading 100,000 random text files.
This is not an official Oracle product and is provided as-is without any warranty.
Use at your own risk and ensure proper testing before use in production environments.
"""

import oci
import argparse
import logging
import threading
import concurrent.futures
import random
import string
import os
from typing import List, Tuple
from concurrent.futures import Future

# Configure logging with thread name
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Create an OCI archive bucket and upload 100,000 random text files.')
    parser.add_argument('--bucket-name', required=True, help='Name of the OCI bucket to create')
    parser.add_argument('--compartment-id', required=True, help='OCID of the compartment')
    parser.add_argument('--profile', default='DEFAULT', help='OCI config profile name')
    parser.add_argument('--max-workers', type=int, default=10, help='Max number of concurrent upload threads (default: 10)')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Print upload operations without executing (default: True)')
    parser.add_argument('--no-dry-run', dest='dry_run', action='store_false', help='Execute upload operations')
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

def create_archive_bucket(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                         bucket_name: str, compartment_id: str) -> None:
    """Create an archive-mode bucket."""
    try:
        client.create_bucket(
            namespace_name=namespace,
            create_bucket_details=oci.object_storage.models.CreateBucketDetails(
                name=bucket_name,
                compartment_id=compartment_id,
                storage_tier='Archive'
            )
        )
        logger.info(f"Successfully created archive bucket: {bucket_name}")
    except oci.exceptions.ServiceError as e:
        if e.status == 409 and 'BucketAlreadyExists' in str(e):
            logger.warning(f"Bucket {bucket_name} already exists, proceeding with uploads")
        else:
            logger.error(f"Failed to create bucket {bucket_name}: {e}")
            raise

def generate_random_path_and_content() -> Tuple[str, str]:
    """Generate a random file path and text content."""
    # Generate random directory structure (1 to 3 levels deep)
    depth = random.randint(1, 3)
    path_parts = []
    for _ in range(depth):
        folder_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        path_parts.append(folder_name)
    
    # Generate random file name
    file_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12)) + '.txt'
    path_parts.append(file_name)
    object_path = '/'.join(path_parts)
    
    # Generate random text content (50-200 bytes)
    content_length = random.randint(50, 200)
    content = ''.join(random.choices(string.ascii_letters + string.digits + ' \n', k=content_length))
    
    return object_path, content

def upload_object(client: oci.object_storage.ObjectStorageClient, namespace: str, 
                 bucket_name: str, object_name: str, content: str, dry_run: bool) -> None:
    """Upload a single object or print the operation for dry-run."""
    if dry_run:
        logger.info(f"DRY RUN: Would upload object {object_name} with {len(content)} bytes")
        return
    
    try:
        client.put_object(
            namespace_name=namespace,
            bucket_name=bucket_name,
            object_name=object_name,
            put_object_body=content.encode('utf-8')
        )
        logger.info(f"Successfully uploaded object: {object_name}")
    except oci.exceptions.ServiceError as e:
        logger.error(f"Failed to upload object {object_name}: {e}")

def update_progress(future: Future, total: int, counter: List[int], lock: threading.Lock) -> None:
    """Callback to update progress when an upload task completes."""
    with lock:
        counter[0] += 1
        logger.info(f"Upload progress: {counter[0]}/{total} objects uploaded")

def main():
    """Main function to create bucket and upload random objects."""
    args = parse_arguments()
    
    try:
        # Initialize OCI client
        client = get_object_storage_client(args.profile)
        
        # Get namespace
        namespace = get_namespace(client)
        logger.info(f"Retrieved namespace: {namespace}")
        
        # Create archive bucket
        if not args.dry_run:
            logger.info(f"Creating archive bucket {args.bucket_name}")
            create_archive_bucket(client, namespace, args.bucket_name, args.compartment_id)
        else:
            logger.info(f"DRY RUN: Would create archive bucket {args.bucket_name}")
        
        # Generate and upload 100,000 objects
        total_objects = 100_000
        logger.info(f"Starting upload of {total_objects} objects")
        objects_to_upload = [generate_random_path_and_content() for _ in range(total_objects)]
        
        counter = [0]  # Mutable counter for tracking completed tasks
        lock = threading.Lock()  # Lock for thread-safe counter updates
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = [
                executor.submit(
                    upload_object,
                    client,
                    namespace,
                    args.bucket_name,
                    object_name,
                    content,
                    args.dry_run
                )
                for object_name, content in objects_to_upload
            ]
            
            # Add callback for progress updates
            for future in futures:
                future.add_done_callback(
                    lambda f: update_progress(f, total_objects, counter, lock)
                )
            
            # Wait for all upload operations to complete
            concurrent.futures.wait(futures)
        
        logger.info(f"All {total_objects} upload operations {'simulated' if args.dry_run else 'completed'}")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    main()