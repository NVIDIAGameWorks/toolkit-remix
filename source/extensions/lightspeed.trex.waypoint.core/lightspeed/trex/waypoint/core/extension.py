import carb
import omni.ext
from lightspeed.common.constants import WINDOW_NAME as _WINDOW_NAME
from lightspeed.trex.contexts import get_instance as get_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from lightspeed.trex.viewports.shared.widget import get_viewport_api
from omni.kit.waypoint.core.extension import get_instance as get_waypoint_instance

g_singleton = None


def get_instance():
    return g_singleton


class WaypointExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.waypoint.core] Startup")
        contexts = get_contexts_instance()
        try:
            context = contexts.get_current_context()
        except RuntimeError:
            context = _Contexts.STAGE_CRAFT

        global g_singleton
        try:
            g_singleton = get_waypoint_instance()
            g_singleton.set_viewport_widget(get_viewport_api(context.value))
            g_singleton.set_main_window_name(_WINDOW_NAME)
        except TypeError:
            g_singleton = None

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.waypoint.core] Shutdown")
        global g_singleton
        g_singleton = None
