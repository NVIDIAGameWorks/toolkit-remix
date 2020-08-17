import os
import sys
import logging
import argparse
import atexit

logger = logging.getLogger(os.path.basename(__file__))


def main():
    import repoman

    repoman.bootstrap()
    import omni.repo.man
    import omni.repo.licensing

    # setting up the teamcity blocks
    omni.repo.man.open_teamcity_block("Licensing", f"Kit Extention {os.getenv('BUILD_NUMBER', '0')}")
    atexit.register(omni.repo.man.close_teamcity_block, "Licensing")

    omni.repo.licensing.main()


if __name__ == "__main__":
    main()
