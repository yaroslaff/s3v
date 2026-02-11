import argparse
import sys
from pathlib import Path
from botocore.exceptions import NoCredentialsError, ClientError, ParamValidationError

from ..aws import list_buckets, delete_from_s3, upload_to_s3, download_from_s3, undelete_from_s3, recover_object_version, wipe_from_s3
from ..ls import list_objects

def get_args():    
    parser = argparse.ArgumentParser(description="S3V CLI")
    parser.add_argument("COMMAND", choices=["ls", "cp", "rm", "del", "delete", "recover", "rec", "r", "unrm", "wipe"], help="The command to execute: ls, cp, rm, recover")
    parser.add_argument("LOCATION1", nargs='?', help="The S3 or local location (e.g. s3://bucket/key or bucket/prefix or arhive.zip)")
    parser.add_argument("LOCATION2", nargs='?', help="The S3 location for cp command (e.g., s3://bucket/key or bucket/prefix)")

    parser.add_argument("--profile", help="AWS CLI profile to use for authentication")
    parser.add_argument("-r", "--recursive", action="store_true", default=False, help="List all objects recursively (only for ls command)")
    parser.add_argument("-s", "--version", metavar='S3_OBJECT_VERSION', help="Version specifier for rm and recover commands")
    parser.add_argument("-e", "--etag", default=False, action="store_true", help="Print ETag (md5sum) for each version in ls command")
    parser.add_argument("-b", "--batch", default=False, action="store_true", help="Batch mode (minimal output, suitable for scripting)")

    return parser.parse_args()

def guess_if_upload(loc1: str, loc2: str) -> bool | None:
    """Guess if the cp command is an upload or download based on the presence of s3:// and existence of local files."""
    loc1_is_s3 = loc1.startswith("s3://")
    loc2_is_s3 = loc2.startswith("s3://")

    if loc1_is_s3 and not loc2_is_s3:
        return False  # Download
    elif loc2_is_s3 and not loc1_is_s3:
        return True  # Upload
    else:
        # If both are local paths, guess based on file existence
        if Path(loc1).exists() and not Path(loc2).exists():
            return True  # Upload
        elif Path(loc2).exists() and not Path(loc1).exists():
            return False  # Download
        else:
            return None  # Ambiguous, cannot guess





def main():
    args= get_args()
    
    try:
        if args.COMMAND == "ls":
            if args.LOCATION1 is None:
                list_buckets(profile_name=args.profile)
                return
            
            list_objects(bucket=args.LOCATION1, profile_name=args.profile, recursive=args.recursive, etag=args.etag, batch=args.batch)
            return
        elif args.COMMAND == "cp":
            if args.LOCATION1 is None or args.LOCATION2 is None:
                print("Error: cp command requires both source and destination locations.", file=sys.stderr)
                return
            if args.LOCATION1.startswith("s3://") and args.LOCATION2.startswith("s3://"):
                print("Error: cp command does not support copying between two S3 locations. Please copy to/from local filesystem instead.", file=sys.stderr)
                return
            
            
            if guess_if_upload(args.LOCATION1, args.LOCATION2):
                    upload_to_s3(source=args.LOCATION1, destination=args.LOCATION2, profile_name=args.profile)
                    return
            else:
                download_from_s3(s3obj=args.LOCATION1, destination=args.LOCATION2, version_id=args.version, profile_name=args.profile)
                return                    

        elif args.COMMAND in ["rm", "del", "delete"]:
            delete_from_s3(s3obj=args.LOCATION1, version_id=args.version, profile_name=args.profile)
            return
        elif args.COMMAND == "wipe":    
            wipe_from_s3(s3obj=args.LOCATION1, profile_name=args.profile)
            return
        elif args.COMMAND in ["recover", "rec", "r", "undelete", "undel", "unrm"]:
            if args.version:
                # recover specific version
                recover_object_version(s3obj=args.LOCATION1, version_id=args.version, profile_name=args.profile)
            else:
                # just recover the latest version if version is not specified
                undelete_from_s3(s3obj=args.LOCATION1, profile_name=args.profile)
            return
        else:
            print("Do not know how to handle command:", args.COMMAND, file=sys.stderr)
            sys.exit(1)

    except (NoCredentialsError, ClientError, ParamValidationError) as botocore_error:
        print(f"Botocore Error: {botocore_error}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()