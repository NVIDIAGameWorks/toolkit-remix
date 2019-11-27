import os
import sys
import logging
import packmanapi

# Set it to your local repo_man repo path for development mode.
REPO_MAN_DEVELOPMENT_FOLDER = None  # "C:/projects/repo/repo_man"

REPO_MAN_VERSION = "0.1.11"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
HOST_DEPS_PATH = os.path.join(SCRIPT_DIR, "../../_build/host-deps")


def configure_logging():
    """
    Configure default logging.
    """

    # Replace current default handler with stdout handler and setup formatting
    root_logger = logging.getLogger()
    root_logger.handlers = []

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s][%(name)s] %(message)s"))
    root_logger.addHandler(handler)

    # Set log levels
    root_logger.setLevel(logging.INFO)
    logging.getLogger("packman").setLevel(logging.WARN)
    logging.getLogger("omni.repo").setLevel(logging.INFO)


def bootstrap():
    """
    Bootstrap omni.repo.man (repo_man module).

    Install and source link into specified host-deps folder using packman, add it to sys.path.
    You can `import omni.repo.man` after calling that function.

    Note:
        Change `REPO_MAN_DEVELOPMENT_FOLDER` to your path if you want to use local repo_man instead.
    """
    configure_logging()

    # Install Repo Man
    repoman_link_path = os.path.abspath(os.path.join(HOST_DEPS_PATH, "repo_man"))

    if REPO_MAN_DEVELOPMENT_FOLDER:
        packmanapi.link(repoman_link_path, REPO_MAN_DEVELOPMENT_FOLDER)
    else:
        packmanapi.install("repo_man", package_version=REPO_MAN_VERSION, link_path=repoman_link_path)
    if repoman_link_path not in sys.path:
        sys.path.append(repoman_link_path)
