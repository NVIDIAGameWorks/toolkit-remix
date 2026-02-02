# SPDX-FileCopyrightText: Copyright (c) 2021-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import contextlib
import io
import json
import os
import sys
from http.client import HTTPSConnection
from urllib.parse import urlparse

import packmanapi

REPO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../..")
REPO_DEPS_FILE = os.path.join(REPO_ROOT, "deps/repo-deps.packman.xml")

## START CUSTOM BOOTSTRAP CODE ##

# Download the remote dependency files and pull the packages using packman
INTERNAL_DEPENDENCIES = [
    (
        "https://gitlab-master.nvidia.com/api/v4/projects/131876/repository/files/deps%2Frepo-deps.packman.xml/raw?ref=main",
        os.path.join(REPO_ROOT, "deps/repo-deps-internal.packman.xml"),
    ),
]
# Download the remote files and take no further action
INTERNAL_DOWNLOADS = [
    (
        "https://gitlab-master.nvidia.com/api/v4/projects/131876/repository/files/repo.toml/raw?ref=main",
        os.path.join(REPO_ROOT, "repo_internal.toml"),
    ),
    (
        "https://gitlab-master.nvidia.com/api/v4/projects/131876/repository/files/source%2Fshell%2Fopen_project.bat/raw?ref=main",
        os.path.join(REPO_ROOT, "source/shell/open_project.bat"),
    ),
    (
        "https://gitlab-master.nvidia.com/api/v4/projects/131876/repository/files/source%2Fshell%2Fopen_project.sh/raw?ref=main",
        os.path.join(REPO_ROOT, "source/shell/open_project.sh"),
    ),
]

def is_host_reachable(url: str, timeout: float = 2):
    """
    Check if the host of a URL is reachable. Does not check if the specific file exists.

    Args:
        url: The URL whose host to check.
        timeout: The timeout in seconds.
    """
    connection = None
    try:
        parsed_url = urlparse(url)
        host = parsed_url.netloc or parsed_url.path.split("/")[0]
        connection = HTTPSConnection(host, timeout=timeout)
        connection.request("HEAD", "/")
        response = connection.getresponse()
        return response.status < 400
    except Exception:  # noqa
        return False
    finally:
        if connection:
            connection.close()


class GitBlobHashCache:
    """Context manager for caching git blob hashes with auto-save on exit."""

    _CACHE_FILE = os.path.join(REPO_ROOT, ".git-blob-hash-cache.json")

    def __init__(self):
        self._data = {}
        self._modified = False

    def __enter__(self):
        if os.path.exists(self._CACHE_FILE):
            try:
                with open(self._CACHE_FILE, encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:  # noqa
                print(f"Warning: Failed to load git blob hash cache: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._modified:
            try:
                with open(self._CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
            except Exception as e:  # noqa
                print(f"Warning: Failed to save git blob hash cache: {e}")
        return False

    @staticmethod
    def _get_gitlab_file_hash(url: str, timeout: float = 5) -> tuple[str | None, bool]:
        """
        Get the blob_id (git content hash) for a file from GitLab API.

        Converts a raw file URL to the metadata endpoint and retrieves the blob_id,
        which is the git SHA-1 hash of the file content.

        Returns:
            A tuple of (hash, file_accessible).
            - hash: The blob_id if successfully retrieved, None otherwise.
            - file_accessible: False if the file doesn't exist (404), True otherwise.
        """
        # Convert raw URL to metadata URL by removing /raw from the path
        metadata_url = url.replace("/raw?", "?")
        connection = None
        try:
            parsed_url = urlparse(metadata_url)
            host = parsed_url.netloc
            path = parsed_url.path + ("?" + parsed_url.query if parsed_url.query else "")

            connection = HTTPSConnection(host, timeout=timeout)
            connection.request("GET", path)
            response = connection.getresponse()

            if response.status == 404:
                return None, False

            if response.status != 200:
                return None, True

            data = json.loads(response.read().decode("utf-8"))
            return data.get("blob_id"), True
        except Exception:  # noqa
            return None, True
        finally:
            if connection:
                connection.close()

    def download_if_needed(self, url: str, local_path: str) -> bool:
        """
        Download file if it needs updating based on git hash comparison.

        Args:
            url: The remote file URL.
            local_path: The local file path.

        Returns:
            True if the file was downloaded, False otherwise.
        """
        remote_hash, file_accessible = self._get_gitlab_file_hash(url)

        if not file_accessible:
            print(f"Warning: Remote file not accessible: {url}")
            return False

        if remote_hash is None:
            print(f"Warning: Could not retrieve remote file hash: {url}")
            return False

        needs_download = (
            not os.path.exists(local_path)  # File doesn't exist locally
            or remote_hash != self._data.get(url)  # Hash changed
        )

        if needs_download:
            packmanapi.get_file(url, local_path)
            self._data[url] = remote_hash
            self._modified = True

        return needs_download


## END CUSTOM BOOTSTRAP CODE ##

def bootstrap():
    """
    Bootstrap all omni.repo modules.

    Pull with packman from repo.packman.xml and add them all to python sys.path to enable importing.
    """

    # START CUSTOM BOOTSTRAP CODE

    deps_files = [REPO_DEPS_FILE]

    with GitBlobHashCache() as cache:
        for url, local_path in INTERNAL_DEPENDENCIES:
            if is_host_reachable(url):
                cache.download_if_needed(url, local_path)
            if os.path.exists(local_path):
                deps_files.append(local_path)

        for url, local_path in INTERNAL_DOWNLOADS:
            if is_host_reachable(url):
                cache.download_if_needed(url, local_path)

    # END CUSTOM BOOTSTRAP CODE

    with contextlib.redirect_stdout(io.StringIO()):
        for deps_file in deps_files:
            deps = packmanapi.pull(deps_file)
            for dep_path in deps.values():
                if dep_path not in sys.path:
                    sys.path.append(dep_path)


if __name__ == "__main__":
    bootstrap()
    import omni.repo.man

    omni.repo.man.main(REPO_ROOT)
