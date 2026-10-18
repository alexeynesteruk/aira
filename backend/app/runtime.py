"""Shared runtime paths, kept consistent between the server and CLI tools."""

import os
from pathlib import Path


def default_data_dir() -> Path:
    """The local data directory: ``AIRA_DATA_DIR``, else ``<repo>/data/app``."""
    return Path(
        os.environ.get(
            "AIRA_DATA_DIR",
            Path(__file__).resolve().parents[2] / "data" / "app",
        )
    )
