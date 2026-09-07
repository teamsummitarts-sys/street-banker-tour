"""Storage evidence for the separately mounted Room module."""
import os
from pathlib import Path


def on_persistent_disk(directory):
    """Render's disk must actually be mounted; a directory name is not proof."""
    root = Path('/var/data')
    directory = Path(directory).resolve()
    return os.path.ismount(root) and all(
        path.resolve().is_relative_to(root)
        for path in (directory, directory / 'songs.sqlite3', directory / 'audio')
    )
