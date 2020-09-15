import os
import sys

import carb
import omni.kit.app


def run():
    # Load app plugin
    carb.get_framework().load_plugins(
        loaded_file_wildcards=["omni.kit.app.plugin"], search_paths=["${CARB_APP_PATH}/plugins"]
    )
    app = omni.kit.app.get_app_interface()

    # Start the default Kit Experience App
    return app.run("omniverse-kit", os.environ["CARB_APP_PATH"], sys.argv)
