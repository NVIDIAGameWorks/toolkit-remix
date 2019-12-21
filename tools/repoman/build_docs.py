import os
import sys
import argparse

import packmanapi
import repoman
repoman.bootstrap()
import omni.repo.man


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))


def build_documentation(config_dir: str, input_dir: str, output_dir: str):
    import sphinx.cmd.build
    print(f"\n*** Building docs ({output_dir}) ***")
    args = ['-c', config_dir, '-b', 'html', input_dir, output_dir]
    exit_code = sphinx.cmd.build.main(args)

    if exit_code:
        print(f"!!! Error while building docs !!!")
        sys.exit(exit_code)    


def main():
    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", dest="config", required=False, default="debug")
    options = parser.parse_args()

    paths = omni.repo.man.get_repo_paths(ROOT_DIR)

    omni.repo.man.pip_install("sphinx", paths["pip_packages"])
    omni.repo.man.pip_install("sphinx_rtd_theme", paths["pip_packages"])

    #os.environ["PATH"] += f"{ROOT_DIR}/_build/{platform_host}/{options.config}"
    sys.path.append(f"{ROOT_DIR}/_build/{platform_host}/{options.config}/extensions")

    build_documentation(paths["docs_src"], paths["docs_src"], paths["docs_dst"])


if __name__ == "__main__":
    main()