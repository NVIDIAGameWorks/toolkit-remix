import datetime
import asyncio
import os, sys

import carb
import omni.kit.app


def run():
    # Load app plugin
    carb.get_framework().load_plugins(
        loaded_file_wildcards=["omni.kit.app.plugin"], search_paths=["${CARB_APP_PATH}/plugins"]
    )
    app = omni.kit.app.get_app_interface()

    # Task to connect and open stage
    async def task():
        import omni.kit.asyncapi

        await omni.kit.asyncapi.connect("ov-sandbox.nvidia.com:3009", "test", "test")
        await omni.kit.asyncapi.open_stage("omni:/Projects/Dev/MdlTest2/CubesAndSpheres.usda")

    asyncio.ensure_future(task())

    # Run Default Kit, that will eventually start event loop and the task above
    return app.run("omniverse-kit", os.environ["CARB_APP_PATH"], sys.argv)
