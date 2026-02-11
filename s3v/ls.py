from pathlib import Path
import json

from .aws import normalize_bucket_name, sync_versions
from .versions import VersionsIndex


def list_objects(bucket: str, prefix: str = "", profile_name=None, recursive: bool = False, etag: bool = False, batch: bool = False):
    """List objects in a specific S3 bucket and prefix."""

    bucket, prefix = normalize_bucket_name(bucket)
    vi = sync_versions(bucket, profile_name=profile_name)

    # vi.dump()

    # vi = VersionsIndex.load_from_file(Path.home() / ".cache" / "s3v" / bucket / "versions.json")


    # exact match
    if prefix in vi:
        print(f"Objects under prefix '{prefix}':")
        vo = vi[prefix]
        #print("OLD:")
        #print(json.dumps(vo.serialize(), indent=2))
        #print()
        #print("NEW:")
        print(vo.ls_versions(strip_prefix=prefix, etag=etag))
        return

    # prefix list

    if prefix and not prefix.endswith("/"):
        prefix += "/"

    for key in sorted(vi.keys()):
        if key.startswith(prefix):
            if batch:
                print(key)
            else:
                print(vi[key].ls_1line(strip_prefix=prefix))
