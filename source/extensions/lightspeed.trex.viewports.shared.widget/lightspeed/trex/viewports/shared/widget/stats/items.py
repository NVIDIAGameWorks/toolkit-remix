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

__all__ = [
    "ViewportDeviceStat",
    "ViewportFPS",
    "ViewportHostStat",
    "ViewportMessage",
    "ViewportProgress",
    "ViewportResolution",
    "ViewportSpeed",
    "ViewportStatsGroup",
]

import traceback
import weakref
from collections.abc import Callable, Sequence

import carb
import omni.ui as ui
from omni.gpu_foundation_factory import get_memory_info

from .settings import (
    CAM_SPEED_MESSAGE_KEY,
    IRAY_MAX_SAMPLES,
    MEMORY_CHECK_FREQUENCY,
    RTX_ACCUMULATED_LIMIT,
    RTX_ACCUMULATION_ENABLED,
    RTX_PT_TOTAL_SPP,
    RTX_SPP,
    TOAST_MESSAGE_KEY,
)
from .utils import human_readable_size, resolve_hud_visibility

try:
    from omni.hydra.engine.stats import get_device_info
except ImportError:
    get_device_info = None


class ViewportStatistic:
    def __init__(
        self,
        stat_name: str,
        setting_key: str = None,
        parent=None,
        alignment: ui.Alignment = ui.Alignment.RIGHT,
        viewport_api=None,
    ):
        self.__stat_name = stat_name
        self.__labels = []
        self.__alignment = alignment
        self.__ui_obj = self._create_ui(alignment)
        self.__subscription_id: carb.settings.SubscriptionId | None = None
        self.__setting_key: str | None = None

        if setting_key:
            settings = carb.settings.get_settings()
            self.__setting_key, self.visible = resolve_hud_visibility(viewport_api, setting_key, settings)

            # Watch for per-viewport changes to persistent setting to control visibility
            self.__subscription_id = settings.subscribe_to_node_change_events(
                self.__setting_key, self._visibility_change
            )
            self._visibility_change(None, carb.settings.ChangeEventType.CHANGED)

    def _visibility_change(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type == carb.settings.ChangeEventType.CHANGED:
            self.visible = bool(carb.settings.get_settings().get(self.__setting_key))

    @property
    def container(self):
        return self.__ui_obj

    def _create_ui(self, alignment: ui.Alignment):
        return ui.VStack(name="Stack", height=0, style_type_name_override="ViewportStats", alignment=alignment)

    def _create_label(self, text: str = "", alignment: ui.Alignment | None = None):
        if alignment is None:
            alignment = self.alignment
        return ui.Label(text, name="Label", style_type_name_override="ViewportStats", alignment=alignment)

    def _destroy_labels(self):
        for label in self.__labels:
            label.destroy()
        self.__labels = []
        self.__ui_obj.clear()
        # Workaround an issue where space is left where the stat was
        if self.__ui_obj.visible:
            self.__ui_obj.visible = False
            self.__ui_obj.visible = True

    def update(self, update_info: dict):
        if self.skip_update(update_info):
            return

        stats = self.update_stats(update_info)
        # If no stats, clear all the labels now
        if not stats:
            self._destroy_labels()
            return

        # If the number of stats has gotten less, need to rebuild it all
        index, n_stats = 0, len(stats)
        if n_stats < len(self.__labels):
            self._destroy_labels()

        for txt in stats:
            self.set_text(txt, index)
            index = index + 1

    def skip_update(self, update_info: dict):
        return False

    def update_stats(self, update_info: dict):
        return ()

    def set_text(self, txt: str, index: int):
        # If the number of stats has grown, add a new label
        if index >= len(self.__labels):
            with self.container:
                self.__labels.append(self._create_label())
        ui_obj = self.__labels[index]
        ui_obj.text = txt
        ui_obj.visible = txt != ""
        return ui_obj

    def destroy(self):
        if self.__labels:
            self._destroy_labels()
            self.__labels = None
        if self.__ui_obj:
            self.__ui_obj.destroy()
            self.__ui_obj = None
        if self.__subscription_id:
            carb.settings.get_settings().unsubscribe_to_change_events(self.__subscription_id)
            self.__subscription_id = None
        self.__setting_key = None

    @property
    def empty(self) -> bool:
        return not bool(self.__labels)

    @property
    def alignment(self) -> ui.Alignment:
        return self.__alignment

    @property
    def visible(self) -> bool:
        return self.__ui_obj.visible

    @visible.setter
    def visible(self, value):
        self.__ui_obj.visible = value

    @property
    def categories(self):
        return ("stats",)

    @property
    def name(self):
        return self.__stat_name


class ViewportDeviceStat(ViewportStatistic):
    def __init__(self, **kwargs):
        super().__init__("Device Memory", setting_key="deviceMemory", **kwargs)
        self.__low_memory = []
        self.__enabled = []

    def skip_update(self, update_info: dict):
        return update_info[MEMORY_CHECK_FREQUENCY]

    def update_stats(self, update_info: dict):
        stat_list = []
        dev_info = get_device_info()
        self.__low_memory = []
        self.__enabled = []

        device_mask = update_info["viewport_api"].frame_info.get("device_mask")

        for desc_idx, dev_memory in zip(range(len(dev_info)), dev_info):
            available = 0
            budget, usage = dev_memory["budget"], dev_memory["usage"]
            if budget > usage:
                available = budget - usage
            self.__low_memory.append((available / budget) < update_info["low_mem_fraction"])
            description = dev_memory["description"] or (f"GPU {desc_idx}")
            if not description:
                description = "GPU " + desc_idx

            self.__enabled.append(device_mask is not None and (device_mask & (1 << desc_idx)))

            used = human_readable_size(usage)
            available = human_readable_size(available)
            stat_list.append(f"{description}: {used} used, {available} available")

        return stat_list

    def set_text(self, txt: str, index: int):
        ui_obj = super().set_text(txt, index)
        if not ui_obj:
            return
        if not self.__enabled[index]:
            ui_obj.name = "LabelDisabled"
        elif self.__low_memory[index]:
            ui_obj.name = "LabelError"
        else:
            ui_obj.name = "Label"


class ViewportHostStat(ViewportStatistic):
    def __init__(self, **kwargs):
        super().__init__("Host Memory", setting_key="hostMemory", **kwargs)
        self.__low_memory = False

    def skip_update(self, update_info: dict):
        return update_info[MEMORY_CHECK_FREQUENCY]

    def update_stats(self, update_info: dict):
        host_info = get_memory_info()
        total, available = host_info["total_memory"], host_info["available_memory"]
        used = total - available
        self.__low_memory = (available / total) < update_info["low_mem_fraction"]
        return [f"Host Memory: {human_readable_size(used)} used, {human_readable_size(available)} available"]

    def set_text(self, txt: str, index: int):
        ui_obj = super().set_text(txt, index)
        if ui_obj:
            ui_obj.name = "LabelError" if self.__low_memory else "Label"


class ViewportFPS(ViewportStatistic):
    def __init__(self, **kwargs):
        super().__init__("FPS", setting_key="renderFPS", **kwargs)
        self.__fps = None
        self.__multiplier = 1
        self.__precision = 2

    def skip_update(self, update_info: dict):
        # FPS update ignores freeze_frame as a signal that rendering is continuing.
        fps = round(update_info["viewport_api"].fps, self.__precision)
        multiplier = update_info["viewport_api"].frame_info.get("subframe_count", 1)
        should_skip_update = True
        if fps != self.__fps:
            self.__fps = fps
            should_skip_update = False
        if multiplier != self.__multiplier:
            self.__multiplier = multiplier
            should_skip_update = False
        return should_skip_update

    def update_stats(self, update_info: dict):
        effective_fps = self.__fps * self.__multiplier
        multiplier = max(self.__multiplier, 1)
        ms = 1000 / effective_fps if effective_fps else 0
        multiplier_str = "," if multiplier == 1 else (" " + ("|" * (multiplier - 1)))
        return [f"FPS: {effective_fps:.{self.__precision}f}{multiplier_str} Frame time: {ms:.{self.__precision}f} ms"]


class ViewportResolution(ViewportStatistic):
    def __init__(self, **kwargs):
        super().__init__("Resolution", setting_key="renderResolution", **kwargs)
        self.__resolution = None

    def skip_update(self, update_info: dict):
        viewport_api = update_info["viewport_api"]
        # If Viewport is frozen to a frame, keep reolution displayed for that frame
        if viewport_api.freeze_frame:
            return True
        resolution = viewport_api.resolution
        if resolution == self.__resolution:
            return True
        self.__resolution = resolution
        return False

    def update_stats(self, update_info: dict):
        return [f"{self.__resolution[0]}x{self.__resolution[1]}"]


class ViewportProgress(ViewportStatistic):
    def __init__(self, **kwargs):
        super().__init__("Progress", setting_key="renderProgress", **kwargs)
        self.__last_accumulated = 0
        self.__total_elapsed = 0

    def skip_update(self, update_info: dict):
        # If Viewport is frozen to a frame, don't update progress, what's displayed should be the last valid
        # progress we have
        return update_info["viewport_api"].freeze_frame

    def update_stats(self, update_info: dict):
        viewport_api = update_info["viewport_api"]
        total, accumulated = None, viewport_api.frame_info.get("progression", None)
        if accumulated is None:
            return []

        label = "PathTracing"
        decimal_places = 2
        no_limit = None
        renderer = viewport_api.hydra_engine
        settings = carb.settings.get_settings()
        if renderer == "rtx":
            render_mode = settings.get("/rtx/rendermode")
            if render_mode == "PathTracing":
                total = settings.get(RTX_PT_TOTAL_SPP)
                no_limit = 0
            elif settings.get(RTX_ACCUMULATION_ENABLED):
                label = "Progress"
                total = settings.get(RTX_ACCUMULATED_LIMIT)
        elif renderer == "iray":
            total = settings.get(IRAY_MAX_SAMPLES)
            no_limit = -1
        if total is None:
            return []

        rtx_spp = settings.get(RTX_SPP)
        if rtx_spp is None:
            return []

        if accumulated <= rtx_spp:
            self.__last_accumulated = 0
            self.__total_elapsed = 0
        elif (self.__last_accumulated < total) or (no_limit is not None and total <= no_limit):
            self.__total_elapsed = self.__total_elapsed + update_info["elapsed_time"]
        self.__last_accumulated = accumulated
        return [f"{label}: {accumulated}/{total} spp : {self.__total_elapsed:.{decimal_places}f} sec"]


class _HudMessageTime:
    def __init__(self, key: str):
        self.__message_time: float = 0
        self.__message_fade_in: float = 0
        self.__message_fade_out: float = 0
        self.__settings_subs: Sequence[carb.settings.SubscriptionId] = None
        self.__init(key)

    def __init(self, key: str):
        time_key: str = f"{key}/seconds"
        fade_in_key: str = f"{key}/fadeIn"
        fade_out_key: str = f"{key}/fadeOut"

        settings = carb.settings.get_settings()
        settings.set_default(time_key, 3)
        settings.set_default(fade_in_key, 0.5)
        settings.set_default(fade_out_key, 0.5)

        def timing_changed(*args, **kwargs):
            self.__message_time = settings.get(time_key)
            self.__message_fade_in = settings.get(fade_in_key)
            self.__message_fade_out = settings.get(fade_out_key)

        timing_changed()

        self.__settings_subs = (
            settings.subscribe_to_node_change_events(time_key, timing_changed),
            settings.subscribe_to_node_change_events(fade_in_key, timing_changed),
            settings.subscribe_to_node_change_events(fade_out_key, timing_changed),
        )

    def __del__(self):
        self.destroy()

    def destroy(self):
        if self.__settings_subs:
            settings = carb.settings.get_settings()
            for sub in self.__settings_subs:
                settings.unsubscribe_to_change_events(sub)
            self.__settings_subs = None

    @property
    def message_time(self) -> float:
        return self.__message_time

    @property
    def message_fade_in(self) -> float:
        return self.__message_fade_in

    @property
    def message_fade_out(self) -> float:
        return self.__message_fade_out

    @property
    def total_up_time(self):
        return self.message_fade_in + self.message_time


class _HudMessageTracker:
    """Calculate alpha for _HudMessageTime acounting for possibility of reversing direction mid-fade"""

    def __init__(self, prev_tckr: _HudMessageTracker | None = None, message_time: _HudMessageTime | None = None):
        self.time: float = 0
        if prev_tckr and message_time:
            # If previous object was fading in, keep alpha
            if prev_tckr.time < message_time.message_fade_in:
                self.time = prev_tckr.time
                return
            # If previous object was fading out, also keep alpha, but reverse direction
            total_msg_up_time = message_time.total_up_time
            if prev_tckr.time > total_msg_up_time:
                self.time = prev_tckr.time - total_msg_up_time
                return
            # If previous object is already being shown at 100%, keep alpha 1
            self.time = message_time.message_fade_in

    def update(self, message_time: _HudMessageTime, elapsed_time: float):
        self.time += elapsed_time
        if self.time < message_time.message_fade_in:
            if message_time.message_fade_in <= 0:
                return 1
            return min(1, self.time / message_time.message_fade_in)
        total_msg_up_time = message_time.total_up_time
        if self.time > total_msg_up_time:
            if message_time.message_fade_out <= 0:
                return 0
            return max(0, 1.0 - (self.time - total_msg_up_time) / message_time.message_fade_out)
        return 1


class ViewportStatisticFading(ViewportStatistic):
    def __init__(self, anim_key: str, *, parent=None, **kwargs):
        super().__init__(**kwargs)
        self.__message_time = _HudMessageTime(anim_key)
        self.__update_sub = None
        self.__alpha = 0
        self.__parent = parent

    def __del__(self):
        self.destroy()

    def destroy(self):
        self.__update_sub = None
        if self.__message_time:
            self.__message_time.destroy()
            self.__message_time = None
        super().destroy()

    def _skip_update(self, update_info: dict, check_empty: Callable | None = None):
        # Skip updates when calld from the render-update, but return the cached alpha
        if update_info.get("external_update") is None:
            alpha = self.__alpha
            update_info["alpha"] = alpha
            if alpha <= 0:
                self.__update_sub = None
            return True

        # Skip any update if no message to display
        is_empty = check_empty() if check_empty else False
        if is_empty:
            update_info["alpha"] = 0
            self.__update_sub = None
        return is_empty

    def _update_alpha(self, update_info: dict, accumulate_alpha: Callable):
        alpha = 0
        elapsed_time = update_info["elapsed_time"]
        if elapsed_time:
            alpha = accumulate_alpha(self.__message_time, elapsed_time, alpha)
        update_info["alpha"] = alpha
        if alpha <= 0:
            self.__update_sub = None
            self.visible = False
        else:
            self.visible = True
        return alpha

    def _begin_animation(self):
        # Add the updtae subscription so that messages / updates are received even when not rendering
        if self.__update_sub:
            return

        def on_update(event: carb.events.IEvent):
            # Build a dict close enough to the render-update info
            update_info = {
                "elapsed_time": event.payload["dt"],
                "alpha": 1,
                "external_update": True,  # Internally tells skip_update to not skip this update
            }
            # Need to call through via parent ViewportStatsGroup to do the alpha adjustment
            self.__parent.update_stats(update_info)
            # Cache the updated alpha to be applied later, but kill the subscription if 0
            self.__alpha = update_info.get("alpha")

        import omni.kit.app  # noqa: PLC0415

        self.__update_sub = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(
                on_update, name=f"omni.kit.viewport.window.stats.ViewportStatisticFading[{self.name}]"
            )
        )

    def _end_animation(self, alpha: float = 0):
        self.__update_sub = None
        self.__alpha = alpha

    @property
    def message_time(self) -> _HudMessageTime:
        return self.__message_time


class ViewportSpeed(ViewportStatisticFading):
    __CAM_VELOCITY = "/persistent/app/viewport/camMoveVelocity"
    __CAMERA_MANIP_MODE = "/exts/omni.kit.manipulator.camera/viewportMode"
    __COLLAPSE_CAM_SPEED = "/persistent" + f"{CAM_SPEED_MESSAGE_KEY}/collapsed"

    def __init__(self, viewport_api, **kwargs):
        self.__carb_subs: Sequence[carb.settings.SubscriptionId] = None
        self.__cam_speed_entry: ui.FloatField | None = None
        self.__cam_speed_model_sub: carb.Subscription | None = None
        self.__viewport_id: str = str(viewport_api.id)
        self.__root_frame: ui.Frame | None = None
        self.__tracker: _HudMessageTracker | None = None
        self.__focused_viewport: bool = False

        super().__init__(
            CAM_SPEED_MESSAGE_KEY,
            stat_name="Camera Speed",
            setting_key="cameraSpeed",
            viewport_api=viewport_api,
            **kwargs,
        )

    def update(self, update_info: dict):
        if self._skip_update(update_info):
            return

        def accumulate_alpha(message_time: _HudMessageTime, elapsed_time: float, _alpha: float):
            if not self.__tracker:
                self.__track_time()
            return self.__tracker.update(message_time, elapsed_time)

        self._update_alpha(update_info, accumulate_alpha)

    def _create_ui(self, alignment: ui.Alignment):
        ui_root = super()._create_ui(alignment=alignment)

        with ui_root:
            self.__root_frame = ui.Frame(build_fn=self.__build_root_ui)
            self.__build_root_ui()
            ui_root.set_mouse_hovered_fn(self.__mouse_hovered)

        return ui_root

    def __track_time(self):
        self.__tracker = _HudMessageTracker(self.__tracker, self.message_time)
        self._begin_animation()

    def __toggle_cam_speed_info(self):
        # Reset the timer tracking on ui interaction
        self.__track_time()
        # Toggle the persistan setting
        settings = carb.settings.get_settings()
        setting_key = self.__COLLAPSE_CAM_SPEED
        collapsed = not bool(settings.get(setting_key))
        settings.set(setting_key, collapsed)

    def __build_cam_speed_info(self, *args, **kwargs):
        mouse_tip = "Using Mouse wheel during flight navigation will adjust how fast or slow the camera will travel"
        ctrl_tip = (
            "Pressing and holding Ctrl button during flight navigation will decrease the speed the camera travels"
        )
        shft_tip = (
            "Pressing and holding Shift button during flight navigation will increase the speed the camera travels"
        )
        with ui.VStack():
            ui.Spacer(height=10)
            with ui.HStack():
                with ui.VStack(alignment=ui.Alignment.CENTER):
                    with ui.HStack():
                        ui.Spacer(width=10)
                        ui.ImageWithProvider(
                            width=30, height=30, style_type_name_override="MouseImage", tooltip=mouse_tip
                        )
                    ui.Label(
                        "Speed", alignment=ui.Alignment.CENTER, style_type_name_override="ViewportStats", name="Label"
                    )

                ui.Spacer(width=10)
                ui.Line(width=2, alignment=ui.Alignment.V_CENTER, style_type_name_override="IconSeparator")
                ui.Spacer(width=10)

                with ui.VStack(alignment=ui.Alignment.CENTER):
                    with ui.ZStack():
                        ui.Rectangle(width=50, height=25, style_type_name_override="KeyboardKey", tooltip=ctrl_tip)
                        ui.Label(
                            "ctrl",
                            alignment=ui.Alignment.CENTER,
                            style_type_name_override="KeyboardLabel",
                            tooltip=ctrl_tip,
                        )
                    ui.Spacer(height=5)
                    ui.Label(
                        "Slow", alignment=ui.Alignment.CENTER, style_type_name_override="ViewportStats", name="Label"
                    )

                ui.Spacer(width=10)
                ui.Line(width=2, alignment=ui.Alignment.V_CENTER, style_type_name_override="IconSeparator")
                ui.Spacer(width=10)

                with ui.VStack(alignment=ui.Alignment.CENTER):
                    with ui.ZStack():
                        ui.Rectangle(width=50, height=25, style_type_name_override="KeyboardKey", tooltip=shft_tip)
                        ui.Label(
                            "shift",
                            alignment=ui.Alignment.CENTER,
                            style_type_name_override="KeyboardLabel",
                            tooltip=shft_tip,
                        )
                    ui.Spacer(height=5)
                    ui.Label(
                        "Fast", alignment=ui.Alignment.CENTER, style_type_name_override="ViewportStats", name="Label"
                    )

    def __build_root_ui(self, collapsed: bool | None = None):
        if collapsed is None:
            collapsed = bool(carb.settings.get_settings().get(self.__COLLAPSE_CAM_SPEED))
        with self.__root_frame:
            with ui.VStack():
                with ui.HStack(alignment=ui.Alignment.LEFT):
                    ui.Button(
                        width=20,
                        name="ExpandButton" if collapsed else "CollapseButton",
                        style_type_name_override="ExpandCollapseButton",
                        clicked_fn=self.__toggle_cam_speed_info,
                    )
                    ui.Label("Camera Speed:", style_type_name_override="ViewportStats", name="Label")
                    self.__cam_speed_entry = ui.FloatField(
                        style_type_name_override="ViewportStats", name="FloatField", width=55
                    )
                    ui.Spacer()

                    def model_changed(model: ui.AbstractValueModel):
                        try:
                            # Compare the values with a precision to avoid possibly excessive recursion
                            settings = carb.settings.get_settings()
                            model_value, carb_value = model.as_float, settings.get(self.__CAM_VELOCITY)
                            if round(model_value, 6) == round(carb_value, 6):
                                return
                            # Short-circuit carb event handling in __cam_vel_changed
                            self.__focused_viewport = False
                            settings.set(self.__CAM_VELOCITY, model_value)
                        finally:
                            self.__focused_viewport = True
                            # Reset the animation counter
                            self.__track_time()

                    model = self.__cam_speed_entry.model
                    self.__cam_speed_entry.precision = 3
                    model.set_value(self.__get_camera_speed_value())
                    self.__cam_speed_model_sub = model.subscribe_value_changed_fn(model_changed)

                if not collapsed:
                    self.__build_cam_speed_info()

    def __get_camera_speed_value(self):
        return carb.settings.get_settings().get(self.__CAM_VELOCITY) or 0

    def __cam_manip_mode_changed(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type == carb.settings.ChangeEventType.CHANGED:
            manip_mode = carb.settings.get_settings().get(self.__CAMERA_MANIP_MODE)
            if manip_mode and manip_mode[0] == self.__viewport_id:
                self.__focused_viewport = True
                if manip_mode[1] == "fly":
                    self.__track_time()
            else:
                self.__focused_viewport = False

    def __collapse_changed(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if self.__root_frame and event_type == carb.settings.ChangeEventType.CHANGED:
            self.__root_frame.rebuild()

    def __cam_vel_changed(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if self.__cam_speed_entry and self.__focused_viewport and event_type == carb.settings.ChangeEventType.CHANGED:
            self.__cam_speed_entry.model.set_value(self.__get_camera_speed_value())
            self.__track_time()

    def __mouse_hovered(self, hovered: bool, *args):
        if hovered:
            self._end_animation(1)
        else:
            self._begin_animation()

    def _visibility_change(self, item: carb.dictionary.Item, event_type: carb.settings.ChangeEventType):
        if event_type != carb.settings.ChangeEventType.CHANGED:
            return

        settings = carb.settings.get_settings()
        super()._visibility_change(item, event_type)
        if self.visible:
            # Made visible, setup additional subscriptions need now
            if self.__carb_subs is None:
                self.__carb_subs = (
                    settings.subscribe_to_node_change_events(self.__CAM_VELOCITY, self.__cam_vel_changed),
                    settings.subscribe_to_node_change_events(
                        f"{self.__CAMERA_MANIP_MODE}/1", self.__cam_manip_mode_changed
                    ),
                    settings.subscribe_to_node_change_events(self.__COLLAPSE_CAM_SPEED, self.__collapse_changed),
                )
                # Handle init case from super()__init__, only want the subscritions setup, not to show the dialog
                if item is not None:
                    self.__focused_viewport = True
                    self.__cam_vel_changed(None, carb.settings.ChangeEventType.CHANGED)
        elif self.__carb_subs:
            # Made invisible, remove uneeded subscriptions now
            self.__remove_camera_subs(settings)
            self._end_animation()

    def __remove_camera_subs(self, settings):
        carb_subs, self.__carb_subs = self.__carb_subs, None
        if carb_subs:
            for carb_sub in carb_subs:
                settings.unsubscribe_to_change_events(carb_sub)

    def destroy(self):
        self.__tracker = None
        if self.__root_frame:
            self.__root_frame.destroy()
            self.__root_frame = None
        self.__remove_camera_subs(carb.settings.get_settings())
        if self.__cam_speed_model_sub:
            self.__cam_speed_model_sub = None
        if self.__cam_speed_entry:
            self.__cam_speed_entry.destroy()
            self.__cam_speed_entry = None
        super().destroy()

    @property
    def empty(self) -> bool:
        return False


class ViewportMessage(ViewportStatisticFading):
    class _ToastMessage(_HudMessageTracker):
        """Store a message to fade with _HudMessageTracker"""

        def __init__(self, message: str, *args, **kwargs):
            self.__message = message
            super().__init__(*args, **kwargs)

        @property
        def message(self):
            return self.__message

    def __init__(self, **kwargs):
        super().__init__(TOAST_MESSAGE_KEY, stat_name="Toast Message", setting_key="toastMessage", **kwargs)
        self.__messages = {}

    def skip_update(self, update_info: dict):
        return self._skip_update(update_info, lambda: not bool(self.__messages))

    def update_stats(self, update_info: dict):
        def accumulate_alpha(message_time: _HudMessageTime, elapsed_time: float, alpha: float):
            self.__messages, messages = {}, self.__messages
            for msg_id, msg in messages.items():
                cur_alpha = msg.update(message_time, elapsed_time)
                if cur_alpha:
                    alpha = max(cur_alpha, alpha)
                    self.__messages[msg_id] = msg
            return alpha

        self._update_alpha(update_info, accumulate_alpha)
        return [obj.message for obj in self.__messages.values()]

    def destroy(self):
        super().destroy()
        self.__messages = {}

    def add_message(self, message: str, message_id: str):
        self.__messages[message_id] = ViewportMessage._ToastMessage(
            message, prev_tckr=self.__messages.get(message_id), message_time=self.message_time
        )
        # Add the update subscription so that messages / updates are received even when not rendering
        self._begin_animation()

    def remove_message(self, message: str, message_id: str):
        if message_id in self.__messages:
            del self.__messages[message_id]


class ViewportStatsGroup:
    def __init__(self, factories, name: str, alignment: ui.Alignment, viewport_api):
        self.__alpha = 0
        self.__stats = []
        self.__group_name = name
        self.__container = ui.ZStack(name="Root", width=0, height=0, style_type_name_override="ViewportStats")
        proxy_self = weakref.proxy(self)
        with self.__container:
            ui.Rectangle(name="Background", style_type_name_override="ViewportStats")
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack(name="Group", style_type_name_override="ViewportStats"):
                    ui.Spacer(height=ui.Pixel(8))
                    for stat_obj in factories:
                        self.__stats.append(stat_obj(parent=proxy_self, alignment=alignment, viewport_api=viewport_api))
                    ui.Spacer(height=ui.Pixel(8))
                ui.Spacer(width=ui.Pixel(8))

        self.__container.visible = False

    def __del__(self):
        self.destroy()

    def destroy(self):
        if self.__stats:
            for stat in self.__stats:
                stat.destroy()
            self.__stats = []
        if self.__container:
            self.__container.clear()
            self.__container.destroy()
            self.__container = None

    def __set_alpha(self, alpha: float):
        alpha = min(0.8, alpha)
        if alpha == self.__alpha:
            return

        self.__alpha = alpha
        self.__container.set_style(
            {
                "ViewportStats::Background": {
                    "background_color": ui.color(0.145, 0.157, 0.165, alpha),
                    "border_radius": 4,
                },
                "ViewportStats::Label": {"color": ui.color(1.0, 1.0, 1.0, alpha)},
                "ViewportStats::LabelError": {"color": ui.color(1.0, 0.0, 0.0, alpha)},
                "ViewportStats::LabelWarning": {"color": ui.color(1.0, 1.0, 0.0, alpha)},
                "MouseImage": {
                    "color": ui.color(1.0, 1.0, 1.0, alpha),
                },
                "IconSeparator": {
                    "color": ui.color(0.431, 0.431, 0.431, alpha),
                },
                "ExpandCollapseButton.Image::ExpandButton": {
                    "color": ui.color(0.102, 0.569, 0.772, alpha),
                },
                "ExpandCollapseButton.Image::CollapseButton": {
                    "color": ui.color(0.102, 0.569, 0.772, alpha),
                },
                "KeyboardKey": {
                    "border_color": ui.color(0.102, 0.569, 0.772, alpha),
                },
                "KeyboardLabel": {
                    "color": ui.color(0.102, 0.569, 0.772, alpha),
                },
                "ViewportStats::FloatField": {
                    "color": ui.color(1.0, 1.0, 1.0, alpha),
                    "background_selected_color": ui.color(0.431, 0.431, 0.431, alpha),
                },
            }
        )
        self.__container.visible = alpha > 0

    def update_stats(self, update_info: dict):
        alpha = 0
        any_visible = False
        for stat in self.__stats:
            try:
                update_info["alpha"] = 1
                stat.update(update_info)
                any_visible = any_visible or (stat.visible and not stat.empty)
                alpha = max(alpha, update_info["alpha"])
            except Exception:  # noqa: BLE001
                carb.log_error(f"Error updating stats {stat}. Traceback:\n{traceback.format_exc()}")

        alpha = alpha if any_visible else 0
        self.__set_alpha(alpha)
        return alpha

    @property
    def visible(self):
        return self.__container.visible

    @visible.setter
    def visible(self, value):
        self.__container.visible = value

    @property
    def categories(self):
        return ("stats",)

    @property
    def name(self):
        return self.__group_name

    @property
    def layers(self):
        yield from self.__stats
