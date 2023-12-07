"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
from typing import TYPE_CHECKING, List

import carb.input
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.app.style import update_viewport_menu_style
from lightspeed.trex.viewports.properties_pane.widget import EnumItems as _PropertiesPaneEnumItems
from lightspeed.trex.viewports.properties_pane.widget import SetupUI as _PropertiesPaneSetupUI
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.kit.viewport.utility import frame_viewport_prims as _frame_viewport_prims
from omni.kit.viewport.utility import frame_viewport_selection as _frame_viewport_selection

from .layers import ViewportLayers

if TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI


class SetupUI:

    viewport_counts = {}

    def __init__(self, context_name):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_registered": None,
            "_viewport_layers": None,
            "_camera_menu": None,
            "_render_menu": None,
            "_property_panel_frame": None,
            "_properties_pane": None,
            "_splitter_property_viewport": None,
            "_viewport_frame": None,
            "_root_frame": None,
            "_last_property_panel_frame_width_value": None,
            "_last_root_frame_width_value": None,
            "_sub_camera_menu_option_clicked": None,
            "_sub_render_menu_option_clicked": None,
            "_property_panel_frame_spacer": None,
            "_extensions_camera_subscription": None,
            "_extensions_render_subscription": None,
            "_minimize_window_subscription": None,
            "_active_viewport_change_subscription": None,
            "_stage_event_subscription": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self.viewport_id = self.next_unique_viewport_name(self._context_name)
        self.___first_time_show_properties = True
        self._active = False
        self._docked = False

        app = omni.kit.app.get_app_interface()
        ext_manager = app.get_extension_manager()
        self._extensions_camera_subscription = ext_manager.subscribe_to_extension_enable(
            on_enable_fn=lambda _: self._on_menubar_camera_extension_enabled_event(),
            on_disable_fn=lambda _: self._on_menubar_camera_extension_disabled_event(),
            ext_name="lightspeed.trex.viewports.menubar.camera",
            hook_name="lightspeed.trex.viewports.shared.widget camera listener",
        )
        self._extensions_render_subscription = ext_manager.subscribe_to_extension_enable(
            on_enable_fn=lambda _: self._on_menubar_render_extension_enabled_event(),
            on_disable_fn=lambda _: self._on_menubar_render_extension_disabled_event(),
            ext_name="lightspeed.trex.viewports.menubar.render",
            hook_name="lightspeed.trex.viewports.shared.widget render listener",
        )

        app_window = omni.appwindow.get_default_app_window()
        self._minimize_window_subscription = app_window.get_window_minimize_event_stream().create_subscription_to_push(
            self._on_minimized, name=f"lightspeed.trex.viewports.shared.widget.minimize_window_subscription.{self}"
        )

        # connect viewport to active viewport event
        event_manager = _get_event_manager_instance()
        event_manager.register_global_custom_event(GlobalEventNames.ACTIVE_VIEWPORT_CHANGED.value)
        self._active_viewport_change_subscription = event_manager.subscribe_global_custom_event(
            GlobalEventNames.ACTIVE_VIEWPORT_CHANGED.value, self.on_active_viewport_changed
        )

        self._registered = []
        self.__create_ui()
        update_viewport_menu_style()

        # connect viewport to stage events
        self._stage_event_subscription = (
            self.viewport_api.usd_context.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="StageEvent"
            )
        )

    @classmethod
    def next_unique_viewport_name(cls, context_name: str) -> str:
        cls.viewport_counts[context_name] = cls.viewport_counts.setdefault(context_name, 0) + 1
        viewport_name = f"Viewport{cls.viewport_counts[context_name] - 1}"
        if context_name:
            return f"{context_name}/{viewport_name}"
        return viewport_name

    @property
    def viewport_api(self) -> "ViewportAPI":
        return self._viewport_layers.viewport_api

    def __create_ui(self):
        self._root_frame = ui.Frame(computed_content_size_changed_fn=self.__root_size_changed)
        with self._root_frame:
            with ui.ZStack():
                with ui.HStack():

                    self._viewport_frame = ui.Frame(
                        separate_window=False,
                        key_pressed_fn=self._on_viewport_frame_key_pressed,
                        mouse_pressed_fn=self._on_viewport_frame_mouse_pressed,
                        horizontal_clipping=True,
                        vertical_clipping=True,
                    )
                    with self._viewport_frame:
                        self._viewport_layers = ViewportLayers(
                            viewport_id=self.viewport_id, usd_context_name=self._context_name
                        )
                        # pause viewport updates initially
                        self.set_active(False)

                    self._property_panel_frame_spacer = ui.Spacer(width=ui.Pixel(12))

                    self._property_panel_frame = ui.Frame(width=ui.Percent(30))
                    with self._property_panel_frame:
                        self._properties_pane = _PropertiesPaneSetupUI(self._context_name)

                self._splitter_property_viewport = ui.Placer(
                    draggable=True,
                    drag_axis=ui.Axis.X,
                    stable_size=True,
                    offset_x_changed_fn=self._on_property_viewport_splitter_change,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_splitter_property_viewport_mouse_pressed(b),
                    mouse_released_fn=lambda x, y, b, m: self._on_splitter_property_viewport_mouse_released(b),
                )
                with self._splitter_property_viewport:
                    with ui.Frame(build_fn=self.__init_splitter):  # to keep the Z depth order
                        with ui.ZStack(width=ui.Pixel(12), opaque_for_mouse_events=True):
                            ui.Rectangle(name="WorkspaceBackground")
                            with ui.VStack():
                                for _ in range(3):
                                    ui.Image(
                                        "",
                                        name="TreePanelLinesBackground",
                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_CROP,
                                        width=ui.Pixel(12),
                                    )

                            ui.Rectangle(name="TreePanelBackgroundSplitter")

        self.toggle_viewport_property_panel(forced_value=True, value=False)

    def _set_viewport_api_updates_enabled(self):
        """Halt or resume viewport updates depending on state."""
        if not self._viewport_layers or not self._viewport_layers.viewport_api:
            return
        updates_enabled = True
        if self._docked and carb.settings.get_settings().get("/app/renderer/skipWhileMinimized"):
            updates_enabled = False
        if not self._active:
            updates_enabled = False
        self.viewport_api.updates_enabled = updates_enabled

    def _on_minimized(self, event: carb.events.IEvent, *args, **kwargs):
        self._docked = event.payload.get("isMinimized", False)
        self._set_viewport_api_updates_enabled()

    def set_active(self, active: bool):
        """Call this method when a higher level ui element obscures or uncovers this shared viewport widget"""
        self._active = active
        if self._active:
            # send an event to deactivate all other viewports
            _get_event_manager_instance().call_global_custom_event(
                GlobalEventNames.ACTIVE_VIEWPORT_CHANGED.value, self.viewport_id
            )
        self._set_viewport_api_updates_enabled()

    def on_active_viewport_changed(self, viewport_id: str):
        # disable viewport if another has been activated to ensure only there is only one at a time
        if self.viewport_id != viewport_id:
            self.set_active(False)

    def _on_viewport_frame_mouse_pressed(self, x: float, y: float, button: int, modifier: int):
        self.set_active(True)

    def _on_viewport_frame_key_pressed(self, key, _, pressed):
        # F keys
        if key != int(carb.input.KeyboardInput.F) or pressed:
            return
        self.frame_viewport_selection()

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED):
            # If a new stage is opened on the associated usd_context, we want to activate
            # the viewport in order to make sure we always show the current stage.
            self.set_active(True)

    def frame_viewport_selection(self, selection: List[str] = None):
        if selection is None:
            # frame the current selection:
            _frame_viewport_selection(viewport_api=self._viewport_layers.viewport_api)
            return
        _frame_viewport_prims(viewport_api=self._viewport_layers.viewport_api, prims=selection)

    def toggle_viewport_property_panel(self, forced_value: bool = False, value: bool = False):
        if ((forced_value and value) or not self._property_panel_frame.visible) and self.___first_time_show_properties:
            self._property_panel_frame.width = ui.Percent(30)
            self.___first_time_show_properties = False
        self._property_panel_frame.visible = value if forced_value else not self._property_panel_frame.visible
        self._property_panel_frame_spacer.visible = (
            value if forced_value else not self._property_panel_frame_spacer.visible
        )
        self._splitter_property_viewport.visible = (
            value if forced_value else not self._splitter_property_viewport.visible
        )

    def _on_menubar_camera_extension_enabled_event(self):
        # create LSS camera menu. Dynamic to be able to toggle the extension
        from lightspeed.trex.viewports.menubar.camera import get_instance as _get_instance

        self._camera_menu = _get_instance()
        self._sub_camera_menu_option_clicked = self._camera_menu.subscribe_camera_menu_option_clicked(
            self._camera_menu_item_option_clicked
        )

    def _on_menubar_camera_extension_disabled_event(self):
        self._sub_camera_menu_option_clicked = None
        self._camera_menu = None

    def _on_menubar_render_extension_enabled_event(self):
        # create LSS render menu. Dynamic to be able to toggle the extension
        from lightspeed.trex.viewports.menubar.render import get_instance as _get_instance

        self._render_menu = _get_instance()
        self._sub_render_menu_option_clicked = self._render_menu.subscribe_render_menu_option_clicked(
            self._render_menu_item_option_clicked
        )

    def _on_menubar_render_extension_disabled_event(self):
        self._sub_render_menu_option_clicked = None
        self._render_menu = None

    def _camera_menu_item_option_clicked(self, path):
        self.toggle_viewport_property_panel()
        self._properties_pane.show_panel(_PropertiesPaneEnumItems.CAMERA.value)
        camera_frame = self._properties_pane.get_frame(_PropertiesPaneEnumItems.CAMERA)
        if camera_frame:
            camera_frame.refresh(path)

    def _render_menu_item_option_clicked(self, engine_name: str, render_mode: str):
        print((engine_name, render_mode))

    def __init_splitter(self):
        if self._splitter_property_viewport is None:
            return
        self._splitter_property_viewport.offset_x = self._viewport_frame.computed_width

    @_ignore_function_decorator(attrs=["_ignore_root_size_changed"])
    def __root_size_changed(self):
        asyncio.ensure_future(self.__deferred_root_size_changed())

    @omni.usd.handle_exception
    async def __deferred_root_size_changed(self):
        await omni.kit.app.get_app_interface().next_update_async()
        self.__init_splitter()

    @_ignore_function_decorator(attrs=["_ignore_property_viewport_splitter_change"])
    def _on_property_viewport_splitter_change(self, x):
        if x.value < 0:
            self._splitter_property_viewport.offset_x = ui.Pixel(0)
        elif x.value + 12 >= self._root_frame.computed_width:
            self._splitter_property_viewport.offset_x = ui.Pixel(self._root_frame.computed_width - 12)
        elif (
            self._last_root_frame_width_value is not None
            and self._root_frame.computed_width > self._last_root_frame_width_value
        ):
            self._root_frame.width = ui.Pixel(self._last_root_frame_width_value)
        elif (
            self._last_property_panel_frame_width_value is not None  # noqa PLE0203
            and self._property_panel_frame.computed_width == self._last_property_panel_frame_width_value  # noqa PLE0203
        ):
            self._splitter_property_viewport.offset_x = ui.Pixel(self._viewport_frame.computed_width)
        self._last_property_panel_frame_width_value = self._property_panel_frame.computed_width
        asyncio.ensure_future(self.__deferred_on_property_viewport_splitter_change(x))

    def _on_splitter_property_viewport_mouse_pressed(self, button):
        if button != 0:
            return
        self._last_root_frame_width_value = self._root_frame.computed_width

    def _on_splitter_property_viewport_mouse_released(self, button):
        if button != 0:
            return
        self._root_frame.width = ui.Percent(100)
        self._last_root_frame_width_value = None

    @omni.usd.handle_exception
    async def __deferred_on_property_viewport_splitter_change(self, x):
        await omni.kit.app.get_app_interface().next_update_async()
        if self._root_frame is None:
            return
        if x.value < 0:
            x = ui.Pixel(0)
        result = (
            100 - ((x.value / (self._root_frame.computed_width / 100)) + (12 / (self._root_frame.computed_width / 100)))
            if self._root_frame.computed_width > 0
            else 0
        )
        self._property_panel_frame.width = ui.Percent(result)

    def destroy(self):
        _reset_default_attrs(self)
