def kmgt(sz: int) -> str:
    """Convert bytes to human-readable format."""
    if sz < 1024:
        return f"{sz}"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if sz < 1024:
            return f"{sz:.1f}{unit}"
        sz /= 1024
    return f"{sz:.1f}PB"

