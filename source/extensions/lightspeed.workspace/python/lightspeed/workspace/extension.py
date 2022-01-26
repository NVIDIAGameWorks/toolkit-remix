import asyncio
import json

import carb
import omni.client
import omni.ext
import omni.kit.app
import omni.kit.window.toolbar
import omni.ui as ui

_INSTANCE = None


class LightspeedWorkspace:
    class _Event(set):
        """
        A list of callable objects. Calling an instance of this will cause a
        call to each item in the list in ascending order by index.
        """

        def __call__(self, *args, **kwargs):
            """Called when the instance is “called” as a function"""
            # Call all the saved functions
            for f in self:
                f(*args, **kwargs)

        def __repr__(self):
            """
            Called by the repr() built-in function to compute the “official”
            string representation of an object.
            """
            return f"Event({set.__repr__(self)})"

    class _EventSubscription:
        """
        Event subscription.

        _Event has callback while this object exists.
        """

        def __init__(self, event, fn):
            """
            Save the function, the event, and add the function to the event.
            """
            self._fn = fn
            self._event = event
            event.add(self._fn)

        def __del__(self):
            """Called by GC."""
            self._event.remove(self._fn)

    def __init__(self, extension_path):
        self._extension_path = extension_path
        self.__on_workspace_restored = self._Event()

    def _workspace_restored(self):
        """Call the event object that has the list of functions"""
        self.__on_workspace_restored()

    def subscribe_workspace_restored(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return self._EventSubscription(self.__on_workspace_restored, fn)

    def setup_workspace(self):
        workspace_file = f"{self._extension_path}/data/layout.default.json"

        result, _, content = omni.client.read_file(workspace_file)

        if result != omni.client.Result.OK:
            carb.log_error(f"Can't read the workspace file {workspace_file}, error code: {result}")
            return

        data = json.loads(memoryview(content).tobytes().decode("utf-8"))
        asyncio.ensure_future(self._load_layout(data))

    async def _load_layout(self, data):
        # few frames delay to avoid the conflict with the layout of omni.kit.mainwindow
        for _ in range(3):
            await omni.kit.app.get_app().next_update_async()

        ui.Workspace.restore_workspace(data)
        await omni.kit.app.get_app().next_update_async()
        self._workspace_restored()


class LightspeedWorkspaceExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.workspace] Lightspeed Workspace startup")
        # first set up the layout
        extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        global _INSTANCE
        _INSTANCE = LightspeedWorkspace(extension_path)
        _INSTANCE.setup_workspace()

        # remove play button from main toolbar
        toolbar = omni.kit.window.toolbar.toolbar.get_instance()
        play_btn = omni.kit.window.toolbar.builtin_tools.play_button_group
        if toolbar and play_btn:
            toolbar.remove_widget(play_btn)

    def on_shutdown(self):
        carb.log_info("[lightspeed.workspace] Lightspeed Workspace shutdown")


def get_instance():
    return _INSTANCE  # noqa R504
