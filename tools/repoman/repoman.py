import os
import sys
import tempfile
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

import packmanapi
from packman import errors

REPO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../..")
REPO_DEPS_FILE = Path(REPO_ROOT) / "deps" / "repo-deps.packman.xml"
REPO_INTERNAL_DEPS_FILE = REPO_DEPS_FILE.parent / "repo-deps-internal.packman.xml"
OPT_DEPS_FILE = "https://gitlab-master.nvidia.com/api/v4/projects/131876/repository/files/deps%2Frepo-deps.packman.xml/raw?ref=main"
REPO_TOML_PRIVATE = "https://gitlab-master.nvidia.com/api/v4/projects/131876/repository/files/repo.toml/raw?ref=main"
REPO_INTERNAL_TOML_FILE = Path(REPO_ROOT) / "repo_internal.toml"


def is_url_reachable(url: str, timeout: float = 2):
    """
    Check if a URL is reachable.

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


def bootstrap():
    """
    Bootstrap all omni.repo modules.

    Pull with packman from repo.packman.xml and add them all to python sys.path to enable importing.
    """
    files = [REPO_DEPS_FILE]
    if not is_url_reachable(OPT_DEPS_FILE) and REPO_INTERNAL_DEPS_FILE.exists():
        REPO_INTERNAL_DEPS_FILE.unlink()

    # Check if the URL is reachable before pulling the deps to avoid the 1-minute delay
    if is_url_reachable(OPT_DEPS_FILE):
        try:
            packmanapi.get_file(OPT_DEPS_FILE, REPO_INTERNAL_DEPS_FILE)
            files.append(REPO_INTERNAL_DEPS_FILE)
        except (RuntimeError, errors.PackmanError):
            pass
    for file in files:
        if file.is_file():
            deps = packmanapi.pull(file.as_posix())
            for dep_path in deps.values():
                if dep_path not in sys.path:
                    sys.path.append(dep_path)

    # internal repo.toml
    if not is_url_reachable(REPO_TOML_PRIVATE) and REPO_INTERNAL_TOML_FILE.exists():
        REPO_INTERNAL_TOML_FILE.unlink()

    if is_url_reachable(REPO_TOML_PRIVATE):
        try:
            packmanapi.get_file(REPO_TOML_PRIVATE, REPO_INTERNAL_TOML_FILE)
        except (RuntimeError, errors.PackmanError):
            pass


if __name__ == "__main__":
    bootstrap()
    import omni.repo.man

    omni.repo.man.main(REPO_ROOT)
