# SPDX-FileCopyrightText: Copyright (c) 2021-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import contextlib
import fnmatch
import glob
import io
import json
import os
import sys
from http.client import HTTPSConnection
from urllib.parse import quote

import packmanapi

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../.."))
REPO_DEPS_FILE = os.path.join(REPO_ROOT, "deps/repo-deps.packman.xml")

## START CUSTOM BOOTSTRAP CODE ##

GITLAB_HOST = "gitlab-master.nvidia.com"
GITLAB_PROJECT_ID = "131876"
GITLAB_BRANCH = "main"
GITLAB_BASE_URL = f"https://{GITLAB_HOST}/api/v4/projects/{GITLAB_PROJECT_ID}"

# Glob patterns for files to never download (private repo metadata)
SKIP_GLOBS = [
    ".gitignore",
    ".git/**",
]

# Glob patterns for files to skip in CI environments (not needed in packages)
CI_SKIP_GLOBS = [
    "docs_dev/**",
    "source/shell/**",
]

# Glob patterns for packman dependency manifests (pull via packman after download)
PACKMAN_GLOBS = [
    "deps/*.packman.xml",
]


def _matches_any_glob(path: str, patterns: list[str]) -> bool:
    """Check if a path matches any of the given glob patterns."""
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def _remove_file_safe(path: str) -> None:
    """Remove a file if it exists. Silently ignores errors (locked, missing, permissions)."""
    with contextlib.suppress(OSError):
        if os.path.exists(path):
            os.remove(path)


def _to_local_path(file_path: str) -> str:
    """Convert a remote repo-relative path to a normalized local absolute path."""
    return os.path.normpath(os.path.join(REPO_ROOT, file_path.replace("/", os.sep)))


def _to_raw_url(file_path: str) -> str:
    """Build the GitLab raw file download URL for a given repo-relative path."""
    return f"{GITLAB_BASE_URL}/repository/files/{quote(file_path, safe='')}/raw?ref={GITLAB_BRANCH}"


def _is_host_reachable(host: str, timeout: float = 0.5) -> bool:
    """Quick HTTPS reachability check. Short timeout to avoid blocking builds when offline."""
    connection = None
    try:
        connection = HTTPSConnection(host, timeout=timeout)
        connection.request("HEAD", "/")
        return connection.getresponse().status < 400
    except Exception:  # noqa
        print(f"[internal] {host} not reachable (offline or off-VPN), skipping internal sync.")
        return False
    finally:
        if connection:
            connection.close()


def _get_repository_tree(host: str) -> list[tuple[str, str]]:
    """
    List all files in the private GitLab repo via the Repository Tree API.

    Returns (file_path, blob_id) tuples. The blob_id is used for change detection
    without per-file API calls.
    """
    files = []
    page = 1
    max_pages = 200  # Safety limit: 200 × 100 = 20,000 files

    print("[internal] Checking for internal repo updates...")
    connection = HTTPSConnection(host, timeout=15)
    try:
        while page <= max_pages:
            connection.request(
                "GET",
                f"/api/v4/projects/{GITLAB_PROJECT_ID}/repository/tree"
                f"?ref={GITLAB_BRANCH}&recursive=true&per_page=100&page={page}",
            )
            response = connection.getresponse()

            if response.status != 200:
                print(f"[internal] Error: GitLab tree API returned status {response.status}")
                return []

            items = json.loads(response.read().decode("utf-8"))
            if not items:
                break

            files.extend((item["path"], item["id"]) for item in items if item.get("type") == "blob")
            page += 1
    except Exception as e:  # noqa
        print(f"[internal] Error: Failed to list repository tree: {e}")
        return []
    finally:
        connection.close()

    return files


class _BlobHashCache:
    """
    Persisted cache of (url → blob_hash) mappings. On the hot path (nothing changed),
    comparing tree hashes against this cache avoids all file downloads.
    """

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
                print(f"[internal] Warning: Failed to load hash cache: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._modified:
            try:
                with open(self._CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
            except Exception as e:  # noqa
                print(f"[internal] Warning: Failed to save hash cache: {e}")
        return False

    def sync(self, files: list[tuple[str, str]]) -> None:
        """
        Download any files whose blob hash has changed or that are missing locally.
        Skips the download loop entirely if everything is already up-to-date.
        """
        # Fast path: check if all files are present with matching hashes
        needs_sync = False
        for file_path, blob_id in files:
            url = _to_raw_url(file_path)
            if not os.path.exists(_to_local_path(file_path)) or self._data.get(url) != blob_id:
                needs_sync = True
                break

        if not needs_sync:
            print(f"[internal] All {len(files)} internal files are up-to-date.")
            return

        downloaded = 0
        for file_path, blob_id in files:
            url = _to_raw_url(file_path)
            local_path = _to_local_path(file_path)

            if os.path.exists(local_path) and self._data.get(url) == blob_id:
                continue

            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                packmanapi.get_file(url, local_path)
                self._data[url] = blob_id
                self._modified = True
                downloaded += 1
            except Exception as e:  # noqa
                print(f"[internal] Warning: Failed to download {file_path}: {e}")
                _remove_file_safe(local_path)
                self._data.pop(url, None)
                self._modified = True

        print(f"[internal] Synced {downloaded}/{len(files)} internal files.")

    def prune(self, remote_files: list[tuple[str, str]]) -> None:
        """Remove cache entries that no longer exist in the remote tree."""
        remote_urls = {_to_raw_url(fp) for fp, _ in remote_files}
        stale_urls = [url for url in self._data if url not in remote_urls]
        for url in stale_urls:
            self._data.pop(url)
            self._modified = True
        if stale_urls:
            print(f"[internal] Pruned {len(stale_urls)} stale cache entries.")


def _sync_internal_repo(is_ci: bool) -> list[str]:
    """
    Sync files from the private GitLab repo into the local repo.

    Returns a list of local paths to packman manifests that need pulling.
    """
    if not _is_host_reachable(GITLAB_HOST):
        # Offline fallback: collect previously downloaded packman manifests
        manifests = []
        for pattern in PACKMAN_GLOBS:
            for match in glob.glob(os.path.join(REPO_ROOT, pattern)):
                manifests.append(match)
        return manifests

    # List all files in the private repo
    all_files = _get_repository_tree(GITLAB_HOST)

    # Filter: skip unwanted files, validate paths stay within repo root
    repo_root_prefix = REPO_ROOT + os.sep
    files_to_sync = []
    for file_path, blob_id in all_files:
        if _matches_any_glob(file_path, SKIP_GLOBS):
            continue
        if is_ci and _matches_any_glob(file_path, CI_SKIP_GLOBS):
            continue
        if not _to_local_path(file_path).startswith(repo_root_prefix):
            print(f"[internal] Warning: Skipping file with path outside repo root: {file_path}")
            continue
        files_to_sync.append((file_path, blob_id))

    # Download changed files
    with _BlobHashCache() as cache:
        cache.sync(files_to_sync)
        if files_to_sync:
            cache.prune(files_to_sync)

    # Collect packman manifests for dependency resolution
    return [
        _to_local_path(fp)
        for fp, _ in files_to_sync
        if _matches_any_glob(fp, PACKMAN_GLOBS) and os.path.exists(_to_local_path(fp))
    ]


## END CUSTOM BOOTSTRAP CODE ##


def bootstrap():
    """
    Bootstrap all omni.repo modules.

    Pull with packman from repo.packman.xml and add them all to python sys.path to enable importing.
    """
    # START CUSTOM BOOTSTRAP CODE
    deps_files = [REPO_DEPS_FILE]
    deps_files.extend(_sync_internal_repo(bool(os.environ.get("CI") or os.environ.get("GITLAB_CI"))))
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
