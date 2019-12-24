"""RepoMan command to build documentation with sphinx.

    Docs source is in "docs" folder. Results go into "_build/docs".
"""

import os
import sys
import argparse

import packmanapi
import repoman

repoman.bootstrap()
import omni.repo.man


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))


def main():
    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", dest="config", required=False, default="debug")
    options = parser.parse_args()

    paths = omni.repo.man.get_repo_paths(ROOT_DIR)

    # Install sphinx and theme
    omni.repo.man.pip_install("sphinx", paths["pip_packages"])
    omni.repo.man.pip_install("sphinx_rtd_theme", paths["pip_packages"])

    # Add extensions folder and pip packages folder (with sphinx) into PYTHONPATH
    path_to_extensions = f"{ROOT_DIR}/_build/{platform_host}/{options.config}/extensions"
    os.environ["PYTHONPATH"] += os.pathsep.join([paths["pip_packages"], path_to_extensions])

    # Run sphinx module. Use kit_sdk python runner, it already has properly PATH and PYTHONPATH set to enable importing of Kit SDK modules
    config_dir = paths["docs_src"]
    input_dir = paths["docs_src"]
    output_dir = paths["docs_dst"]
    python_args = ["-m", "sphinx", "-c", config_dir, "-b", "html", input_dir, output_dir]
    python_exe = "python.bat" if platform_host == "windows-x86_64" else "python.sh"
    python_path = (
        f"{ROOT_DIR}/_build/target-deps/kit_sdk_{options.config}/_build/{platform_host}/{options.config}/{python_exe}"
    )
    omni.repo.man.run_process([python_path] + python_args, exit_on_error=True)


if __name__ == "__main__":
    main()
