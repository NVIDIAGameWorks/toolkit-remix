import os, sys

import carb
import omni.kit.app


def run():
    # Load app plugin
    carb.get_framework().load_plugins(
        loaded_file_wildcards=["omni.kit.app.plugin"], search_paths=["${CARB_APP_PATH}/plugins"]
    )
    app = omni.kit.app.get_app_interface()

    # Pass experience config:
    example_root = os.environ["EXAMPLE_ROOT"]
    sys.argv.extend(["--config-path", f"{example_root}/apps/example.app.json"])

    return app.run("omniverse-kit", os.environ["CARB_APP_PATH"], sys.argv)
