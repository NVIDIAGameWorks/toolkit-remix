"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import carb
import carb.input
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.hydra.remix.core import REMIX_HYDRA_ENGINE_NAME as _HDREMIX_HYDRA_ENGINE_NAME
from lightspeed.hydra.remix.core import REMIX_RENDER_MODE as _HDREMIX_RENDER_MODE
from lightspeed.hydra.remix.core import REMIX_RENDERERS_SETTING as _HDREMIX_RENDERERS_SETTING
from lightspeed.hydra.remix.core import RemixSupport as _RemixSupport
from lightspeed.hydra.remix.core import is_remix_supported as _is_remix_supported
from lightspeed.hydra.remix.core import retry_remix_support_async as _retry_remix_support_async
from lightspeed.trex.app.style import update_viewport_menu_style
from lightspeed.trex.utils.common.camera import ensure_editable_camera_for_navigation as _ensure_editable_camera
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from lightspeed.trex.utils.widget import WorkspaceWidget as _WorkspaceWidget
from lightspeed.trex.viewports.properties_pane.widget import EnumItems as _PropertiesPaneEnumItems
from lightspeed.trex.viewports.properties_pane.widget import SetupUI as _PropertiesPaneSetupUI
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.kit.viewport.utility import frame_viewport_prims as _frame_viewport_prims
from omni.kit.viewport.utility import frame_viewport_selection as _frame_viewport_selection

from .layers import ViewportLayers

if TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI

_SHOW_REMIX_SUPPORT_POPUP_SETTING = "/exts/lightspeed/hydra/remix/showpopup"
_REMIX_FAILURE_DIALOG_SHOWN = False
_PROPERTY_PANEL_MIN_WIDTH = 240
_PROPERTY_VIEWPORT_SPLITTER_WIDTH = 12


def _show_remix_failure_dialog(error_message: str) -> bool:
    global _REMIX_FAILURE_DIALOG_SHOWN

    if _REMIX_FAILURE_DIALOG_SHOWN:
        return False

    settings = carb.settings.get_settings()
    if not settings.get_as_bool(_SHOW_REMIX_SUPPORT_POPUP_SETTING):
        return False

    def exit_app():
        omni.kit.app.get_app().post_quit(0)

    _TrexMessageDialog(
        title="RTX Remix Renderer failed to initialize",
        message=error_message,
        ok_label="Exit",
        ok_handler=exit_app,
        on_window_closed_fn=exit_app,
        disable_cancel_button=True,
    )
    _REMIX_FAILURE_DIALOG_SHOWN = True
    return True


class SetupUI(_WorkspaceWidget):
    viewport_counts = {}
    _REMIX_TIMEOUT_FRAMES_SETTING = "exts/lightspeed/hydra/remix/startupTimeoutFrames"
    _REMIX_VIEWPORT_STABLE_FRAMES_SETTING = "exts/lightspeed/trex/viewports/shared/widget/remixViewportStableFrames"
    _REMIX_VIEWPORT_STABLE_TIMEOUT_FRAMES_SETTING = (
        "exts/lightspeed/trex/viewports/shared/widget/remixViewportStableTimeoutFrames"
    )
    _REMIX_POST_STABLE_DWELL_FRAMES_SETTING = "exts/lightspeed/trex/viewports/shared/widget/remixPostStableDwellFrames"
    _ACTIVATE_REMIX_RENDERER_SETTING = "exts/lightspeed/trex/viewports/shared/widget/activateRemixRenderer"
    _REMIX_ENGINE_NAME = _HDREMIX_HYDRA_ENGINE_NAME
    _REMIX_RENDER_MODE = _HDREMIX_RENDER_MODE
    _REMIX_RENDERERS_SETTING = _HDREMIX_RENDERERS_SETTING

    def __init__(self, context_name):
        """Nvidia StageCraft Viewport UI"""
        super().__init__()

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
            "_remix_renderer_activation_task": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self.viewport_id = self.next_unique_viewport_name(self._context_name)
        self.___first_time_show_properties = True
        self._active = False
        self._docked = False

        if self._should_activate_remix_renderer():
            self._apply_remix_renderer_settings()

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
    def viewport_api(self) -> ViewportAPI:
        return self._viewport_layers.viewport_api

    @property
    def viewport_layers(self) -> ViewportLayers:
        return self._viewport_layers

    def __create_ui(self):
        self._root_frame = ui.Frame(computed_content_size_changed_fn=self.__root_size_changed)
        with self._root_frame:
            with ui.ZStack():
                with ui.HStack():
                    self._viewport_frame = ui.Frame(
                        separate_window=False,
                        mouse_pressed_fn=self._on_viewport_frame_mouse_pressed,
                        horizontal_clipping=True,
                        vertical_clipping=True,
                    )
                    with self._viewport_frame:
                        self._viewport_layers = ViewportLayers(
                            viewport_id=self.viewport_id,
                            usd_context_name=self._context_name,
                            is_active_fn=self.is_active,
                        )
                        # do viewport updates initially
                        self.set_active(True)

                    self._property_panel_frame_spacer = ui.Spacer(width=ui.Pixel(_PROPERTY_VIEWPORT_SPLITTER_WIDTH))

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
                        with ui.ZStack(width=ui.Pixel(_PROPERTY_VIEWPORT_SPLITTER_WIDTH), opaque_for_mouse_events=True):
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

    def viewport_frame(self):
        return self._viewport_frame

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

    def is_active(self):
        return self._active

    def on_active_viewport_changed(self, viewport_id: str):
        # disable viewport if another has been activated to ensure only there is only one at a time
        if self.viewport_id != viewport_id:
            self.set_active(False)

    def _on_viewport_frame_mouse_pressed(self, x: float, y: float, button: int, modifier: int):
        self.set_active(True)

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED):
            # If a new stage is opened on the associated usd_context, we want to activate
            # the viewport in order to make sure we always show the current stage.
            self.set_active(True)
            self._schedule_remix_renderer_activation("stage-opened")

    def _schedule_remix_renderer_activation(self, reason: str, retry_support: bool = True):
        task = self._remix_renderer_activation_task
        if task is not None and not task.done():
            carb.log_info(
                "[lightspeed.trex.viewports.shared.widget] "
                f"HdRemix renderer activation already scheduled for {self.viewport_id}; "
                f"skipping duplicate request from {reason}."
            )
            return
        self._remix_renderer_activation_task = asyncio.ensure_future(
            self._activate_remix_renderer_async(reason, retry_support=retry_support)
        )

    def _viewport_signature(self) -> tuple[object, ...]:
        viewport_api = self.viewport_api
        stage = viewport_api.stage if viewport_api else None
        stage_identifier = stage.GetRootLayer().identifier if stage else None
        render_product_path = getattr(viewport_api, "render_product_path", None) if viewport_api else None
        render_product_exists = self._render_product_exists(stage, render_product_path)
        return (
            getattr(viewport_api, "id", None) if viewport_api else None,
            getattr(viewport_api, "usd_context_name", None) if viewport_api else None,
            getattr(viewport_api, "hydra_engine", None) if viewport_api else None,
            getattr(viewport_api, "render_mode", None) if viewport_api else None,
            render_product_path,
            getattr(viewport_api, "camera_path", None) if viewport_api else None,
            viewport_api.frame_info.get("viewport_handle") if viewport_api else None,
            render_product_exists,
            stage_identifier,
        )

    @staticmethod
    def _viewport_signature_ready(signature: tuple[object, ...] | None) -> bool:
        return bool(signature) and signature[7] is True and all(value is not None for value in signature)

    @staticmethod
    def _render_product_exists(stage, render_product_path) -> bool | None:
        if not stage or not render_product_path:
            return None
        render_product_prim = stage.GetPrimAtPath(render_product_path)
        return bool(render_product_prim and render_product_prim.IsValid())

    def _is_remix_viewport_renderer_selected(self, viewport_api: ViewportAPI) -> bool:
        return (
            viewport_api.hydra_engine == self._REMIX_ENGINE_NAME and viewport_api.render_mode == self._REMIX_RENDER_MODE
        )

    def _apply_remix_renderer_settings(self) -> None:
        settings = carb.settings.get_settings()
        for setting_path, value in (
            ("/renderer/enabled", self._REMIX_ENGINE_NAME),
            ("/renderer/active", self._REMIX_ENGINE_NAME),
            ("/pxr/rendermode", self._REMIX_RENDER_MODE),
            ("/pxr/renderers", self._REMIX_RENDERERS_SETTING),
        ):
            if settings.get(setting_path) != value:
                settings.set(setting_path, value)

    @staticmethod
    def _should_activate_remix_renderer() -> bool:
        return carb.settings.get_settings().get_as_bool(SetupUI._ACTIVATE_REMIX_RENDERER_SETTING)

    def _activate_remix_viewport_renderer(self, reason: str) -> bool:
        if not self._should_activate_remix_renderer():
            carb.log_info(
                "[lightspeed.trex.viewports.shared.widget] "
                f"Skipping HdRemix renderer activation for {self.viewport_id} during {reason}."
            )
            return False

        viewport_api = self.viewport_api
        if viewport_api is None:
            carb.log_warn(
                "[lightspeed.trex.viewports.shared.widget] "
                f"Cannot activate HdRemix renderer for {self.viewport_id}: viewport API is not ready."
            )
            return False

        self._apply_remix_renderer_settings()

        try:
            set_hd_engine = getattr(viewport_api, "set_hd_engine", None)
            if callable(set_hd_engine):
                set_hd_engine(self._REMIX_ENGINE_NAME, self._REMIX_RENDER_MODE)
            else:
                viewport_api.hydra_engine = self._REMIX_ENGINE_NAME
                viewport_api.render_mode = self._REMIX_RENDER_MODE
        except Exception as exc:  # noqa: BLE001
            message = f"Failed to activate HdRemix renderer for {self.viewport_id} during {reason}: {exc!r}"
            carb.log_warn(f"[lightspeed.trex.viewports.shared.widget] {message}")
            _show_remix_failure_dialog(message)
            return False

        carb.log_info(
            "[lightspeed.trex.viewports.shared.widget] "
            f"Activated HdRemix renderer for {self.viewport_id} during {reason}: "
            f"renderer_selected={self._is_remix_viewport_renderer_selected(viewport_api)!r}, "
            f"signature={self._viewport_signature()!r}"
        )
        return True

    async def _wait_for_stable_viewport(self) -> tuple[object, ...] | None:
        settings = carb.settings.get_settings()
        stable_frame_target = settings.get_as_int(self._REMIX_VIEWPORT_STABLE_FRAMES_SETTING) or 10
        timeout_frames = settings.get_as_int(self._REMIX_VIEWPORT_STABLE_TIMEOUT_FRAMES_SETTING) or 240
        stable_signature = None
        stable_frames = 0

        for frame in range(1, timeout_frames + 1):
            await omni.kit.app.get_app().next_update_async()
            signature = self._viewport_signature()
            signature_ready = self._viewport_signature_ready(signature)
            if signature == stable_signature and signature_ready:
                stable_frames += 1
            else:
                stable_signature = signature
                stable_frames = 1 if signature_ready else 0

            if stable_frames in (1, stable_frame_target):
                carb.log_info(
                    "[lightspeed.trex.viewports.shared.widget] "
                    f"HdRemix viewport stabilization frame={frame}, "
                    f"stable_frames={stable_frames}, signature={signature!r}"
                )

            if stable_frames >= stable_frame_target:
                return stable_signature

        carb.log_warn(
            "[lightspeed.trex.viewports.shared.widget] "
            f"Viewport did not stabilize before HdRemix activation after {timeout_frames} frames. "
            f"Last signature={stable_signature!r}"
        )
        return stable_signature

    async def _activate_remix_renderer_async(self, reason: str, retry_support: bool = True):
        settings = carb.settings.get_settings()
        if not self._should_activate_remix_renderer():
            carb.log_info(
                "[lightspeed.trex.viewports.shared.widget] "
                f"Skipping HdRemix renderer activation for {self.viewport_id} during {reason}."
            )
            return

        self._apply_remix_renderer_settings()

        if not retry_support:
            return

        stable_signature = await self._wait_for_stable_viewport()
        if not self._viewport_signature_ready(stable_signature):
            return

        if not self._activate_remix_viewport_renderer(f"{reason}-stable"):
            return
        dwell_frames = settings.get_as_int(self._REMIX_POST_STABLE_DWELL_FRAMES_SETTING) or 120
        for frame in range(1, dwell_frames + 1):
            await omni.kit.app.get_app().next_update_async()
            if frame in (1, dwell_frames):
                carb.log_info(
                    "[lightspeed.trex.viewports.shared.widget] "
                    f"HdRemix post-stable dwell frame={frame}/{dwell_frames}, "
                    f"signature={self._viewport_signature()!r}"
                )

        await self._retry_remix_support_after_renderer_activation(reason)

    async def _retry_remix_support_after_renderer_activation(self, reason: str):
        support_level, _error_message = _is_remix_supported()
        if support_level == _RemixSupport.SUPPORTED:
            return

        settings = carb.settings.get_settings()
        timeout_frames = settings.get_as_int(self._REMIX_TIMEOUT_FRAMES_SETTING) or 500
        frames_passed = await _retry_remix_support_async(
            timeout_frames=timeout_frames,
            reason=f"{reason} for {self.viewport_id}",
        )
        carb.log_info(
            "[lightspeed.trex.viewports.shared.widget] "
            f"HdRemix support retry for {self.viewport_id} during {reason} took {frames_passed} frame(s)."
        )
        support_level, error_message = _is_remix_supported()
        if support_level == _RemixSupport.NOT_SUPPORTED:
            _show_remix_failure_dialog(error_message)

    def frame_viewport_selection(self, selection: list[str] = None):
        if not _ensure_editable_camera(self._viewport_layers.viewport_api, "Frame/focus"):
            return
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
        from lightspeed.trex.viewports.menubar.camera import get_instance as _get_instance  # noqa: PLC0415

        self._camera_menu = _get_instance()
        self._sub_camera_menu_option_clicked = self._camera_menu.subscribe_camera_menu_option_clicked(
            self._camera_menu_item_option_clicked
        )

    def _on_menubar_camera_extension_disabled_event(self):
        self._sub_camera_menu_option_clicked = None
        self._camera_menu = None

    def _on_menubar_render_extension_enabled_event(self):
        # create LSS render menu. Dynamic to be able to toggle the extension
        from lightspeed.trex.viewports.menubar.render import get_instance as _get_instance  # noqa: PLC0415

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
        # Overwrite the default behavior which is to show a render settings window,
        # because we do not allow any chances to lose the 1:1 with the game.
        pass

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
        max_splitter_offset = max(
            self._root_frame.computed_width - _PROPERTY_VIEWPORT_SPLITTER_WIDTH - _PROPERTY_PANEL_MIN_WIDTH,
            0,
        )
        if x.value < 0:
            x = ui.Pixel(0)
            self._splitter_property_viewport.offset_x = x
        elif x.value > max_splitter_offset:
            x = ui.Pixel(max_splitter_offset)
            self._splitter_property_viewport.offset_x = x
        elif (
            self._last_root_frame_width_value is not None
            and self._root_frame.computed_width > self._last_root_frame_width_value
        ):
            self._root_frame.width = ui.Pixel(self._last_root_frame_width_value)
        elif (
            self._last_property_panel_frame_width_value is not None
            and self._property_panel_frame.computed_width == self._last_property_panel_frame_width_value
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
            100
            - (
                (x.value / (self._root_frame.computed_width / 100))
                + (_PROPERTY_VIEWPORT_SPLITTER_WIDTH / (self._root_frame.computed_width / 100))
            )
            if self._root_frame.computed_width > 0
            else 0
        )
        self._property_panel_frame.width = ui.Percent(result)

    def destroy(self):
        self._mark_destroyed()
        if self._remix_renderer_activation_task is not None and not self._remix_renderer_activation_task.done():
            self._remix_renderer_activation_task.cancel()
        _reset_default_attrs(self)
