from typing import Dict, Any
from pathlib import Path
import json
from datetime import datetime, timezone
import dateparser

from .misc import kmgt


def serialize_version(version_record: Dict) -> Dict:
    # replace LastModified to string
    # make copy of object to avoid mutating original
    version_record = version_record.copy()
    version_record["LastModified"] = version_record["LastModified"].isoformat()
    return version_record

def unserialize_version(version_data: Dict) -> Dict:
    version_data = version_data.copy()
    version_data["LastModified"] = datetime.fromisoformat(version_data["LastModified"])
    return version_data


class VersionedObject:
    def __init__(self, key: str):
        self.key = key
        self.versions = dict()  # version_id -> metadata dict
        self.delete_markers = dict()
    
    def add_version(self, version_record: Dict):
        version_id = version_record["VersionId"]
        self.versions[version_id] = version_record


    def add_delete_marker(self, delete_marker_record: Dict):
        version_id = delete_marker_record["VersionId"]
        self.delete_markers[version_id] = delete_marker_record
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "versions": [serialize_version(v) for v in self.versions.values()],
            "delete_markers": [serialize_version(dm) for dm in self.delete_markers.values()]
        }
    
    def __repr__(self) -> str:
        return f"VersionedObject(key={self.key}, versions={len(self.versions)}, delete_markers={len(self.delete_markers)})"


    def dump(self):
        for version in self.versions.values():
            print(f"  Version: {version}")
        for dm in self.delete_markers.values():
            print(f"  Delete Marker: {dm}")

    def get_latest_version(self) -> Dict | None:
        if not self.versions:
            return None
        return max(self.versions.values(), key=lambda v: v["LastModified"])

    def ls_1line(self, strip_prefix: str | None = None) -> str:
        latest_version = self.get_latest_version()
        if latest_version is None:
            return f"{self.key} (deleted, no versions)"
        

        if strip_prefix and self.key.startswith(strip_prefix):
            display_key = self.key[len(strip_prefix):]
        else:            
            display_key = self.key

        deleted = self.is_deleted()
        status = " [DEL]" if deleted else " "
        return f"{display_key:40}|{latest_version['LastModified'].strftime("%Y-%m-%d %H:%M:%S"):5}|{kmgt(latest_version['Size']):>15}| {len(self.versions):>3}|{status}"


    def ls_versions(self, strip_prefix: str | None = None, etag: bool = False) -> str:
        out = ''
        if self.is_deleted():
            out += f"{self.key} [deleted]\n"
        else:
            out += f"{self.key}\n"

        for version in sorted(self.versions.values(), key=lambda v: v["LastModified"]):
            if strip_prefix and self.key.startswith(strip_prefix):
                display_key = self.key[len(strip_prefix):]
            else:
                display_key = self.key
            out += f"  {display_key} {version['VersionId']} {kmgt(version['Size']):>10}  {version['LastModified'].strftime('%Y-%m-%d %H:%M:%S')}"
            if etag:                
                out += f"  {version['ETag']}"
            out += "\n"
        
        for dm in sorted(self.delete_markers.values(), key=lambda dm: dm["LastModified"]):
            if strip_prefix and self.key.startswith(strip_prefix):
                display_key = self.key[len(strip_prefix):]
            else:
                display_key = self.key
            if dm['IsLatest']:
                deleted_str = "[DELETED]"
            else:                
                deleted_str = "[OLD DM]"
            out += f"  {display_key} {dm['VersionId']} {deleted_str:>10}  {dm['LastModified'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return out

    def is_deleted(self) -> bool:       
        # if any IsLatest in delete markers is true, consider it deleted
        return any(dm.get("IsLatest", False) for dm in self.delete_markers.values())    


    def sorted_versions(self):
        return sorted(self.versions.values(), key=lambda v: v["LastModified"])

    def translate_version(self, verspec: str) -> str | None:
        """Translate a version specifier like 'latest' or 'oldest' to an actual version ID."""


        if verspec in self.versions:
            return verspec  # Already a version ID

        # make versions list sorted by LastModified

        vers = self.sorted_versions()

        if verspec in ["latest", "last", "newest"]:
            return vers[-1]["VersionId"] if vers else None

        elif verspec in ["oldest", "first"]:
            if not self.versions:
                return None
            return vers[0]["VersionId"]
        elif verspec in ["previous", "prev", "p"]:
            if len(vers) < 2:
                return None
            return vers[-2]["VersionId"]
        else:

            dt = dateparser.parse(verspec)
            if dt:
                # make UTC-aware if naive
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                # find the latest version older than the specified datetime
                older_versions = [v for v in vers if v["LastModified"] < dt]
                if older_versions:                    
                    return older_versions[-1]["VersionId"]
                else:
                    return None

            try:
                verpos = int(verspec)
                return vers[verpos]["VersionId"]
            except IndexError:
                raise ValueError(f"Version position {verspec} is out of range for object with {len(vers)} versions.")

            except ValueError:
                # not an integer, not a known keyword, and not a version ID
                raise ValueError(f"Invalid version specifier: {verspec}")



class VersionsIndex:
    """In-memory representation of the versions metadata JSON.

    This class contains no AWS code and only operates on the JSON structure
    produced by `_sync_versions` (mapping of key -> {"versions": [...], "delete_markers": [...]}).
    """

    bucket_keys: Dict[str, VersionedObject]

    def __init__(self, bucketname: str):
        self.bucket_keys = dict()
        self.bucketname = bucketname


    def save(self):
        cache_dir = Path.home() / ".cache" / "s3v" 
        cache_dir.mkdir(parents=True, exist_ok=True)
        cach_file = cache_dir / f"{self.bucketname}.json"

        with open(cach_file, "w") as f:
            json.dump({key: vo.serialize() for key, vo in self.bucket_keys.items()}, f, indent=2)

    def load(self):
        cache_dir = Path.home() / ".cache" / "s3v" 
        cach_file = cache_dir / f"{self.bucketname}.json"

        if not cach_file.exists():
            return

        with open(cach_file, "r") as f:
            raw_data = json.load(f)
            for key, vo_data in raw_data.items():
                vo = VersionedObject(key)
                for version_record in vo_data.get("versions", []):
                    vo.add_version(unserialize_version(version_record))
                for delete_marker_record in vo_data.get("delete_markers", []):
                    vo.add_delete_marker(unserialize_version(delete_marker_record))
                self.bucket_keys[key] = vo


    def keys(self):
        return list(self.bucket_keys.keys())

    def get(self, key: str):
        return self.bucket_keys.get(key)

    def __setitem__(self, key: str, value: VersionedObject):
        self.bucket_keys[key] = value

    def __getitem__(self, key: str) -> VersionedObject:
        return self.bucket_keys[key]
    
    def __contains__(self, key: str):
        return key in self.bucket_keys

    # len()
    def __len__(self):
        return len(self.bucket_keys)
    
    def __repr__(self) -> str:
        return f"VersionsIndex(bucket={self.bucketname}, keys={len(self.bucket_keys)})"

    def has_directory(self, dirname: str) -> bool:
        """Check if any key starts with the given directory name."""
        prefix = dirname
        if not prefix.endswith("/"):
            prefix += "/"
        for key in self.bucket_keys.keys():
            if key.startswith(prefix):
                return True
        return False

    def dump(self):
        for key, vo in self.bucket_keys.items():
            print(f"{key}")
            vo.dump()
            print()
    
    def translate_version(self, key: str, verspec: str) -> str | None:
        vo = self.get(key)

        if not vo:
            raise ValueError(f"Key '{key}' not found in bucket '{self.bucketname}'")
        return vo.translate_version(verspec)