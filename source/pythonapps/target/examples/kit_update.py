import datetime
import os, sys

import carb
import omni.kit.app


def run():
    # Load app plugin
    carb.get_framework().load_plugins(
        loaded_file_wildcards=["omni.kit.app.plugin"], search_paths=["${CARB_APP_PATH}/plugins"]
    )
    app = omni.kit.app.get_app_interface()

    # Update loop, manually measuring dt:
    last_update_t = datetime.datetime.now() - datetime.timedelta(microseconds=16666)
    app.startup("omniverse-kit", os.environ["CARB_APP_PATH"], sys.argv)
    while app.is_running():
        time_now = datetime.datetime.now()
        dt = (time_now - last_update_t).microseconds / 1e6
        last_update_t = time_now
        app.update(dt)

    return app.shutdown()
