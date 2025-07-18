# SPDX-FileCopyrightText: Copyright (c) 2021-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import contextlib
import io
import os
import sys
from http.client import HTTPConnection
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

def is_url_reachable(url: str, timeout: float = 2):
    """
    Check if a URL is reachable. Allows for quick checks without downloading the file.

    Args:
        url: The URL to check.
        timeout: The timeout in seconds.
    """
    connection = None
    try:
        parsed_url = urlparse(url)
        host = parsed_url.netloc or parsed_url.path.split("/")[0]
        connection = HTTPConnection(host, timeout=timeout)
        connection.request("HEAD", "/")
        response = connection.getresponse()
        return response.status < 400
    except Exception:  # noqa
        return False
    finally:
        if connection:
            connection.close()

## END CUSTOM BOOTSTRAP CODE ##

def bootstrap():
    """
    Bootstrap all omni.repo modules.

    Pull with packman from repo.packman.xml and add them all to python sys.path to enable importing.
    """

    # START CUSTOM BOOTSTRAP CODE

    deps_files = [REPO_DEPS_FILE]

    for download in INTERNAL_DEPENDENCIES:
        if not os.path.exists(download[1]) and is_url_reachable(download[0]) :
            packmanapi.get_file(download[0], download[1])
        if os.path.exists(download[1]):
            deps_files.append(download[1])

    for download in INTERNAL_DOWNLOADS:
        if not os.path.exists(download[1]) and is_url_reachable(download[0]):
            packmanapi.get_file(download[0], download[1])

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
