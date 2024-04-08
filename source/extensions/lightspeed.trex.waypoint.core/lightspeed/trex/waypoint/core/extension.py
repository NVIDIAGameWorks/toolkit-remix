import carb
import omni.ext
import omni.usd
from lightspeed.common.constants import WINDOW_NAME as _WINDOW_NAME
from lightspeed.trex.contexts import get_instance as get_contexts_instance
from lightspeed.trex.viewports.shared.widget import get_viewport_api
from omni.kit.waypoint.core.extension import get_instance as get_waypoint_instance

g_singleton = None


def get_instance():
    return g_singleton


class WaypointExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.waypoint.core] Startup")
        contexts = get_contexts_instance()

        global g_singleton
        g_singleton = self

        self.waypoint_obj = None

        try:
            context = contexts.get_current_context()
        except RuntimeError:
            return

        self.create_waypoint_instance(context.value)

    def create_waypoint_instance(self, context_name):
        try:
            self.waypoint_obj = get_waypoint_instance()
            self.waypoint_obj.set_viewport_widget(get_viewport_api(context_name))
            self.waypoint_obj.set_main_window_name(_WINDOW_NAME)
        except TypeError:
            self.waypoint_obj = None

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.waypoint.core] Shutdown")
        global g_singleton
        g_singleton = None
        self.waypoint_obj = None
