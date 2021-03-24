import os
import platform
import argparse
import packmanapi


def get_host_platform() -> str:
    """Get host platform string (platform-arch, E.g.: "windows-x86_64")
    """
    arch = platform.machine()
    if arch == "AMD64":
        arch = "x86_64"
    platform_host = platform.system().lower() + "-" + arch
    return platform_host


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.prog = "autopull"
    parser.description = "Auto pull Kit SDK."
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        required=False,
        default="debug",
        help="Config to run test against (debug or release). (default: %(default)s)",
    )
    options = parser.parse_args()

    script_dir = os.path.dirname(os.path.realpath(__file__))
    packmanapi.pull(
        os.path.join(script_dir, "dev/deps/kit-sdk-override.packman.xml"),
        platform=get_host_platform(),
        include_tags=[options.config],
        tokens={"config": options.config},
    )
