import boto3
import sys
import json
from pathlib import Path
from botocore.exceptions import NoCredentialsError, ClientError
from typing import Optional

from .versions import VersionsIndex, VersionedObject
from .misc import kmgt


def normalize_bucket_name(bucket: str) -> tuple:
    """Parse bucket name and optional prefix from s3:// or bucket/prefix format.
    
    Returns:
        (bucket_name, prefix) tuple
    """
    # Remove s3:// prefix if present
    bucket = bucket.replace("s3://", "")
    
    # Split on first / to separate bucket from prefix
    if "/" in bucket:
        parts = bucket.split("/", 1)
        return parts[0], parts[1]
    
    # Remove trailing slash only if no prefix
    return bucket.rstrip("/"), ""

def list_buckets(profile_name=None):
    """List all S3 buckets."""
    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")
        
        response = s3_client.list_buckets()
        buckets = response.get("Buckets", [])
        
        if not buckets:
            print("No buckets found", file=sys.stderr)
            return
        
        print("Available S3 buckets:")
        for bucket in sorted(buckets, key=lambda x: x["Name"]):
            creation_date = bucket.get("CreationDate", "").isoformat() if bucket.get("CreationDate") else "Unknown"
            print(f"  {bucket['Name']:<50} {creation_date}")
    
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        raise sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        raise sys.exit(1)

def sync_versions(bucket: str, profile_name: str | None = None):
    """Internal function to sync versions from S3."""
    cache_dir = Path.home() / ".cache" / "s3v" / bucket
    cache_dir.mkdir(parents=True, exist_ok=True)

    vi = VersionsIndex(bucket)

    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")

        # print(f"# Fetching version metadata for bucket: {bucket}...")

        paginator = s3_client.get_paginator("list_object_versions")
        pages = paginator.paginate(Bucket=bucket)

        version_count = 0

        for page in pages:
            for version in page.get("Versions", []):
                version['ETag'] = version['ETag'].strip('"')  # Remove quotes from ETag
                key = version["Key"]
                vo = vi[key] if key in vi else VersionedObject(key)
                vo.add_version(version)
                vi[key] = vo
                version_count += 1

            for marker in page.get("DeleteMarkers", []):
                key = marker["Key"]
                vo = vi[key] if key in vi else VersionedObject(key)
                vo.add_delete_marker(marker)
                vi[key] = vo
                version_count += 1

        vi.save()

        # print(f"# Fetched metadata for {version_count} versions from {len(vi)} object(s) in bucket '{bucket}'")

        return vi


    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        sys.exit(1)

def delete_from_s3(s3obj: str, version_id: str | None = None, profile_name: str | None = None):
    """Delete an object or specific version in S3.
    
    If version_id is provided, deletes that specific version.
    Otherwise, creates a delete marker in versioned buckets or deletes the object.
    """


    bucket, key = normalize_bucket_name(s3obj)

    vi = sync_versions(bucket, profile_name=profile_name)

    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")
        
        if version_id:
            print(f"# Deleting version {version_id} {vi.translate_version(key, version_id)} of s3://{bucket}/{key}...")
            s3_client.delete_object(Bucket=bucket, Key=key, VersionId=vi.translate_version(key, version_id))
            print(f"# Successfully deleted version {version_id} of s3://{bucket}/{key}")
        else:
            print(f"# Deleting s3://{bucket}/{key}...")
            response = s3_client.delete_object(Bucket=bucket, Key=key)
            
            if "DeleteMarker" in response and response["DeleteMarker"]:
                print(f"# Successfully marked s3://{bucket}/{key} as deleted")
            else:
                print(f"# Successfully deleted s3://{bucket}/{key}")
        
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        raise sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        raise sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise sys.exit(1)

def wipe_from_s3(s3obj: str, profile_name: str | None = None):
    # delete ALL versions of the object, including delete markers, effectively wiping it from history
    bucket, key = normalize_bucket_name(s3obj)
    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")

        print(f"# Wiping s3://{bucket}/{key} (deleting all versions and delete markers)...")

        # List all versions to find all version IDs and delete marker IDs for the key
        paginator = s3_client.get_paginator("list_object_versions")
        pages = paginator.paginate(Bucket=bucket, Prefix=key)

        version_ids_to_delete = []
        for page in pages:
            for version in page.get("Versions", []):
                if version.get("Key") == key:
                    version_ids_to_delete.append(version.get("VersionId"))
            for marker in page.get("DeleteMarkers", []):
                if marker.get("Key") == key:
                    version_ids_to_delete.append(marker.get("VersionId"))

        if not version_ids_to_delete:
            print(f"Error: No versions or delete markers found for s3://{bucket}/{key}", file=sys.stderr)
            raise sys.exit(1)

        # Delete each version and delete marker by specifying their version IDs
        for vid in version_ids_to_delete:
            s3_client.delete_object(Bucket=bucket, Key=key, VersionId=vid)

        print(f"# Successfully wiped s3://{bucket}/{key} from history (deleted {len(version_ids_to_delete)} versions/delete markers)", file=sys.stderr)
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        raise sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        raise sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise sys.exit(1)



def upload_to_s3(source: str, destination: str, profile_name: str | None = None):


    """Upload a file to S3."""
    # Parse source file
    source_path = Path(source)
    if not source_path.exists():
        print(f"Error: File not found: {source}")
        raise sys.exit(1)
    
    if not source_path.is_file():
        print(f"Error: Not a file: {source}")
        raise sys.exit(1)
    
    # Parse destination
    bucket, prefix = normalize_bucket_name(destination)

    vi = VersionsIndex(bucket)
    vi.load()

    # If destination ends with /, append filename to prefix
    if prefix.endswith("/"):
        key = prefix + source_path.name

    elif vi.has_directory(prefix):
        # If prefix is a known directory in VersionsIndex, treat as directory
        key = prefix.rstrip('/') + "/" + source_path.name
    elif prefix:
        # If prefix is not empty and doesn't end with /, treat it as a full path
        key = prefix
    else:
        # If no prefix, just use filename
        key = source_path.name

    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")
        
        file_size = source_path.stat().st_size
        size_str = kmgt(file_size) if file_size > 0 else "0B"
        
        print(f"# Uploading {source} to s3://{bucket}/{key} ({size_str})...", file=sys.stderr)
        
        s3_client.upload_file(str(source_path), bucket, key)
        
        print(f"# Successfully uploaded to s3://{bucket}/{key}", file=sys.stderr)
        
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        raise sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        raise sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise sys.exit(1)

def download_from_s3(s3obj: str, destination: str, version_id: str | None = None, profile_name: str | None = None):
    """Download a file from S3."""
    bucket, key = normalize_bucket_name(s3obj)
    
    # Parse destination local path
    dest_path = Path(destination)
    
    # If destination is "." (current dir) or ends with "/", use source filename as basename
    if destination == "." or destination.endswith("/"):
        dest_path = dest_path / Path(key).name
    
    # Create parent directory if needed
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    

    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")
        
        print(f"# Downloading s3://{bucket}/{key} >>> {dest_path}...")
        
        extra_args = {}
        if version_id:
            vi = sync_versions(bucket, profile_name=profile_name)
            
            extra_args["VersionId"] = vi.translate_version(key, version_id)
                        
            print(f"  Using version: {extra_args["VersionId"]}")
        
        s3_client.download_file(bucket, key, str(dest_path), ExtraArgs=extra_args if extra_args else None)
        
        file_size = dest_path.stat().st_size
        size_str = kmgt(file_size)
        
        print(f"# Successfully downloaded ({size_str}) to {str(dest_path)}")
        
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        raise sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        raise sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise sys.exit(1)


def undelete_from_s3(s3obj: str, profile_name: str | None = None):
    """Undelete an object in S3 (remove the delete marker in versioned buckets)."""
    bucket, key = normalize_bucket_name(s3obj)

    try:
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")

        print(f"# Undeleting s3://{bucket}/{key}...")

        # List versions to find the latest delete marker for the key
        paginator = s3_client.get_paginator("list_object_versions")
        pages = paginator.paginate(Bucket=bucket, Prefix=key)

        delete_marker_version = None
        for page in pages:
            for marker in page.get("DeleteMarkers", []):
                if marker.get("Key") == key and marker.get("IsLatest"):
                    delete_marker_version = marker.get("VersionId")
                    break
            if delete_marker_version:
                break

        if not delete_marker_version:
            print(f"Error: No delete marker found for s3://{bucket}/{key}", file=sys.stderr)
            raise sys.exit(1)

        # Delete the delete marker by specifying its version ID
        s3_client.delete_object(Bucket=bucket, Key=key, VersionId=delete_marker_version)

        print(f"# Successfully removed delete marker for s3://{bucket}/{key}", file=sys.stderr)

    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure credentials in ~/.aws/ or set AWS_* environment variables.", file=sys.stderr)
        raise sys.exit(1)
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        raise sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise sys.exit(1)
    
def recover_object_version(
    s3obj: str,    
    version_id: str,
    profile_name: Optional[str] = None):


    bucket, key = normalize_bucket_name(s3obj)

    session = boto3.Session(profile_name=profile_name)
    s3_client = session.client("s3")

    vi = sync_versions(bucket, profile_name=profile_name)

    try:
        # Copy the specific version to itself, making it the current version

        version = vi.translate_version(key, version_id)

        copy_source = {
            'Bucket': bucket,
            'Key': key,
            'VersionId': version
        }
        
        _ = s3_client.copy_object(
            CopySource=copy_source,
            Bucket=bucket,
            Key=key
        )
        
        print(f'Successfully recovered version {version} as current version of s3://{bucket}/{key}')
        
    except ClientError as e:
        print(f'Failed to recover version {version_id}: {e}')
        sys.exit(1)
        


