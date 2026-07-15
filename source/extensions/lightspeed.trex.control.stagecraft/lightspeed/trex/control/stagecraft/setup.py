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

import asyncio
from asyncio import ensure_future
from collections.abc import Callable
from contextlib import nullcontext
from functools import partial
from pathlib import Path

import carb
import lightspeed.trex.sidebar as sidebar
import omni.client
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.kit.window.file
import omni.ui
import omni.usd
from omni.kit.viewport.menubar.lighting.menu_container import MenuContainer as _ViewportLightingMenuContainer
from lightspeed.common.constants import GlobalEventNames
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER as _REMIX_CAPTURE_FOLDER
from lightspeed.common.constants import REMIX_DEPENDENCIES_FOLDER as _REMIX_DEPENDENCIES_FOLDER
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.hotkeys import TrexHotkeyEvent as _TrexHotkeyEvent
from lightspeed.trex.hotkeys import get_global_hotkey_manager as _get_global_hotkey_manager
from lightspeed.trex.menu.workfile import get_instance as _get_menu_workfile_instance
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.core import ProjectWizardSchema as _ProjectWizardSchema
from lightspeed.trex.project_wizard.window import WizardTypes as _WizardTypes
from lightspeed.trex.project_wizard.window import get_instance as _get_wizard_instance
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCoreSetup
from lightspeed.trex.stage.core.shared import Setup as _StageCoreSetup
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from lightspeed.trex.utils.widget import show_invalid_deps_rebuild_dialog as _show_invalid_deps_rebuild_dialog
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.symlink import should_confirm_link_path_replacement as _should_confirm_link_path_replacement
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

_TREX_IGNORE_UNSAVED_STAGE_ON_EXIT = "/app/file/trexIgnoreUnsavedOnExit"
_DEFAULT_LAYOUT = "/app/trex/default_layout"

# Capture GPU device-loss / hang hardening.
# A game capture is thousands of small alpha-tested draw-call meshes. Building Opacity Micromaps
# (OMM) for all of them during stage realization can overrun the path tracer's GPU working set and
# fault the Vulkan device (VK_ERROR_DEVICE_LOST) or wedge the main thread. Prim count does NOT
# reliably predict which captures do this (a 599 KB capture froze while larger ones did not), so we
# disable OMM for ANY capture project opened in StageCraft -- OMM is only a render-time optimization
# for alpha-tested geometry, so turning it off never changes visuals and never affects editing or
# asset replacement; it only trades a little alpha-tested render performance for stability. We push
# the override before ``open_stage`` (so it applies before the capture realizes) and keep re-asserting
# it, because dxvk-remix re-applies the capture's OWN graphics preset a few seconds after it realizes
# (re-enabling OMM / the Neural Radiance Cache integrator) WITHOUT touching the carb ``/rtx/*`` nodes,
# so a one-shot override silently loses and the GPU faults ~1 minute later anyway.
_RTX_OPTION_GRAPHICS_PRESET = "rtx.graphicsPreset"
_RTX_OPTION_INTEGRATE_INDIRECT_MODE = "rtx.integrateIndirectMode"
_RTX_OPTION_OMM_ENABLE = "rtx.opacityMicromap.enable"
# dxvk-remix RtxOptions enums: GraphicsPreset 4 == Custom (so the User-layer writes win over the
# Quality preset), IntegrateIndirectMode 1 == ReSTIR GI (off the heavier Neural Radiance Cache).
_RTX_GRAPHICS_PRESET_CUSTOM = "4"
_RTX_INTEGRATE_INDIRECT_MODE_RESTIR = "1"
_RTX_OMM_DISABLED = "0"
# When enabled (default), any capture project is opened with Opacity Micromaps disabled so it cannot
# fault/hang the GPU. Set to false to load captures with OMM enabled (full renderer settings).
_SETTING_AUTO_SAFE_MODE = "/exts/lightspeed.trex.control.stagecraft/autoDisableOpacityMicromaps"
# How often (seconds) to re-assert the renderer overrides while a capture is loaded.
# ``hdremix_set_configvar`` writes straight to the dxvk-remix RtxOptions User layer (it does NOT
# touch carb ``/rtx/*`` or omni.usd), so it cannot trigger the render-settings-reload deadlock, and
# re-pushing an already-current value is a runtime no-op. Set <= 0 to disable the periodic re-assert.
_SETTING_REASSERT_INTERVAL = "/exts/lightspeed.trex.control.stagecraft/opacityMicromapReassertIntervalSeconds"
_DEFAULT_REASSERT_INTERVAL_SECONDS = 5.0


def _set_hdremix_configvar(key: str, value: str):
    """Set an HdRemix (dxvk-remix RtxOptions User-layer) config variable through the runtime bridge."""
    from lightspeed.hydra.remix.core import hdremix_set_configvar as _hdremix_set_configvar  # noqa: PLC0415

    _hdremix_set_configvar(key, value)


class Setup:
    """Wire StageCraft services, menu actions, hotkeys, and startup layout behavior."""

    _SWITCH_CAPTURE_COMMAND_NAME = "SwitchCaptureCommand"
    _DISABLE_STAGE_OPEN_LIGHTING_UNDO = False
    _LIGHTING_STAGE_OPEN_ORIGINAL = None
    # Capture safe-mode bookkeeping. Class-level defaults keep the hooks safe even when a
    # unit test builds Setup via ``__new__`` (bypassing ``__init__``).
    _safe_mode_capture_path = None
    _reassert_watch_task = None

    def __init__(self) -> None:
        """Create StageCraft setup services, subscriptions, and startup layout guards."""
        self._default_attr = {
            "_sub_wizard_completed": None,
            "_stage_core_setup": None,
            "_capture_core_setup": None,
            "_replacement_core_setup": None,
            "_sub_import_capture_layer": None,
            "_sub_import_replacement_layer": None,
            "_sub_open_workfile": None,
            "_layer_manager": None,
            "_sub_menu_workfile_save": None,
            "_sub_menu_workfile_save_as": None,
            "_sub_menu_workfile_undo": None,
            "_sub_menu_workfile_redo": None,
            "_sub_menu_workfile_new_workfile": None,
            "_menu_workfile_instance": None,
            "_sub_key_undo": None,
            "_sub_key_redo": None,
            "_sub_key_save": None,
            "_sub_key_save_as": None,
            "_sub_key_unselect_all": None,
            "_sub_stage_event": None,
            "_context": None,
            "_capture_swap_undo_dialog_open": False,
            # Capture safe-mode bookkeeping
            "_safe_mode_capture_path": None,
            "_reassert_watch_task": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = _TrexContexts.STAGE_CRAFT.value
        self._context = _trex_contexts_instance().get_usd_context(_TrexContexts.STAGE_CRAFT)
        self._layer_manager = _LayerManagerCore(context_name=_TrexContexts.STAGE_CRAFT.value)
        self._menu_workfile_instance = _get_menu_workfile_instance()
        self._stage_core_setup = _StageCoreSetup(self._context_name)
        self._capture_core_setup = _CaptureCoreSetup(self._context_name)
        self._replacement_core_setup = _ReplacementCoreSetup(self._context_name)

        event_manager = _get_event_manager_instance()
        self._sub_import_capture_layer = event_manager.subscribe_global_custom_event(
            GlobalEventNames.IMPORT_LAYER.value, self._on_import_layer
        )
        self._sub_load_workfile = event_manager.subscribe_global_custom_event(
            GlobalEventNames.LOAD_PROJECT_PATH.value, self._on_open_workfile
        )

        hotkey_manager = _get_global_hotkey_manager()
        self._sub_key_undo = hotkey_manager.subscribe_hotkey_event(
            _TrexHotkeyEvent.CTRL_Z, self._on_undo, context=_TrexContexts.STAGE_CRAFT
        )
        self._sub_key_redo = hotkey_manager.subscribe_hotkey_event(
            _TrexHotkeyEvent.CTRL_Y, self._on_redo, context=_TrexContexts.STAGE_CRAFT
        )
        # save and save-as will trigger regardless of the current layout screen
        self._sub_key_save = hotkey_manager.subscribe_hotkey_event(_TrexHotkeyEvent.CTRL_S, self._on_save)
        self._sub_key_save_as = hotkey_manager.subscribe_hotkey_event(_TrexHotkeyEvent.CTRL_SHIFT_S, self._on_save_as)
        self._sub_key_unselect_all = hotkey_manager.subscribe_hotkey_event(_TrexHotkeyEvent.ESC, self._on_unselect_all)

        self._sub_menu_workfile_save = self._menu_workfile_instance.subscribe_save(self._on_save)
        self._sub_menu_workfile_save_as = self._menu_workfile_instance.subscribe_save_as(self._on_save_as)
        self._sub_menu_workfile_undo = self._menu_workfile_instance.subscribe_undo(self._on_undo)
        self._sub_menu_workfile_redo = self._menu_workfile_instance.subscribe_redo(self._on_redo)
        self._sub_menu_workfile_new_workfile = self._menu_workfile_instance.subscribe_create_new_workfile(
            self._on_new_workfile
        )
        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="StagecraftStageEvent"
        )
        self.__sub_sidebar_items = None

        settings = carb.settings.get_settings()
        default_layout = settings.get(_DEFAULT_LAYOUT) or ""
        if default_layout == "stagecraft":
            # Only force the Home Page layout on a genuine first launch. A stale startup Home layout request
            # can otherwise race with project opening and pull the user back to Home after the workspace is
            # already active.
            stage = self._context.get_stage()
            has_open_project = bool(stage and not bool(stage.GetRootLayer().anonymous))
            if not has_open_project:
                load_layout(_get_quicklayout_config(_LayoutFiles.HOME_PAGE))
        self.__install_stage_open_lighting_undo_patch()

    @classmethod
    def __install_stage_open_lighting_undo_patch(cls):
        if cls._LIGHTING_STAGE_OPEN_ORIGINAL is not None:
            return

        # Capture the original as a local so the closure below is immune to
        # ``__uninstall_stage_open_lighting_undo_patch`` setting the class
        # attribute back to ``None``. Event-stream subscriptions hold strong
        # references to this closure; if it dereferences the class attribute
        # at call time, an in-flight stage-open event firing after uninstall
        # crashes with ``TypeError: 'NoneType' object is not callable`` and
        # corrupts the lighting-menu state, which has been observed to
        # cascade into a GPU crash on the ImGui pixel-shader pass.
        original = _ViewportLightingMenuContainer._MenuContainer__on_stage_open  # noqa: SLF001
        cls._LIGHTING_STAGE_OPEN_ORIGINAL = original

        def _on_stage_open_with_undo_disabled(menu_container, menu_context, usd_context_name, usd_context, prev_mode):
            undo_scope = (
                omni.kit.undo.disabled()
                if cls._DISABLE_STAGE_OPEN_LIGHTING_UNDO and usd_context_name == _TrexContexts.STAGE_CRAFT.value
                else nullcontext()
            )
            with undo_scope:
                return original(menu_container, menu_context, usd_context_name, usd_context, prev_mode)

        _ViewportLightingMenuContainer._MenuContainer__on_stage_open = _on_stage_open_with_undo_disabled  # noqa: SLF001

    @classmethod
    def __uninstall_stage_open_lighting_undo_patch(cls):
        if cls._LIGHTING_STAGE_OPEN_ORIGINAL is None:
            return

        _ViewportLightingMenuContainer._MenuContainer__on_stage_open = cls._LIGHTING_STAGE_OPEN_ORIGINAL  # noqa: SLF001
        cls._LIGHTING_STAGE_OPEN_ORIGINAL = None

    @classmethod
    def __set_stage_open_lighting_undo_disabled(cls, value: bool):
        cls._DISABLE_STAGE_OPEN_LIGHTING_UNDO = value

    def prompt_if_unsaved_project(self, callback: Callable[[], None], action_text: str) -> bool:
        """
        Check for unsaved project and offer to save before executing callback

        Returns:
            True if loading right away, False if it will first prompt the user for unsaved progress.
        """

        def on_save_done(result, error):
            if not result or error:
                _TrexMessageDialog(
                    message="An error occurred while saving the project.",
                    disable_cancel_button=True,
                )
                return
            # No errors saving, let's call the next step...
            callback()

        def on_discard():
            # We want to discard any changes anyway so we can clear dirty state to allow fast quit or
            # whatever operation comes next.
            self._context.set_pending_edit(False)
            callback()

        layer_capture = self._layer_manager.get_layer_of_type(_LayerType.capture)
        layer_replacement = self._layer_manager.get_layer_of_type(_LayerType.replacement)
        if layer_capture and layer_replacement and self._context.has_pending_edit():
            # A project is open and has unsaved edits:
            _TrexMessageDialog(
                f"Do you want to save your changes before {action_text}?",
                title="Save Project?",
                ok_label="Save",
                ok_handler=partial(self._on_save, on_save_done=on_save_done),
                middle_label="Save As",
                middle_handler=partial(self._on_save_as, on_save_done=on_save_done),
                disable_middle_button=False,
                middle_2_label="Discard",
                middle_2_handler=on_discard,
                disable_middle_2_button=False,
                disable_cancel_button=False,  # Cancel will just do nothing
            )
            return False

        # If project does not need to be saved, proceed:
        callback()
        return True

    def should_interrupt_shutdown(self) -> bool:
        """
        Implements `lightspeed.event.shutdown_base.InterrupterBase` protocol.

        Show a user prompt and decide whether to continue shutting down the app.

        Returns:
            True to interrupt shutdown, else False
        """
        ignore_unsaved_stage = carb.settings.get_settings().get(_TREX_IGNORE_UNSAVED_STAGE_ON_EXIT) or False
        return (
            (not ignore_unsaved_stage)
            and self._context
            and (self._context.can_close_stage() and self._context.has_pending_edit())
        )

    def interrupt_shutdown(self, shutdown_callback):
        """
        Implements `lightspeed.event.shutdown_base.InterrupterBase` protocol.

        Show a user prompt and decide whether to continue shutting down the app.
        """

        def callback():
            # Clear dirty state to allow shutdown.
            self._context.set_pending_edit(False)
            shutdown_callback(self)

        self.prompt_if_unsaved_project(callback, "closing app")

    def register_sidebar_items(self):
        self.__sub_sidebar_items = sidebar.register_items(
            [
                sidebar.ItemDescriptor(
                    name="Modding",
                    tooltip="Modding",
                    disabled_tooltip="Modding (Only available if a project is opened).",
                    group=sidebar.Groups.LAYOUTS,
                    mouse_released_fn=self.__open_layout,
                    sort_index=0,
                    enabled=False,
                )
            ]
        )
        self._update_modding_button_state()

    def _on_import_layer(self, layer_type: _LayerType, path: str, existing_file: bool = False):
        if layer_type == _LayerType.capture:
            # Disable Opacity Micromaps before the switched-to capture is realized so it cannot
            # fault the GPU, and re-assert the overrides if safe mode is already armed this session.
            self._apply_capture_safe_mode_on_switch(path)
            capture_layer = self._capture_core_setup.get_layer()
            requested_capture_identifier = omni.client.normalize_url(path) if path else None
            current_capture_identifier = capture_layer.identifier if capture_layer else None
            if current_capture_identifier is None:
                self._capture_core_setup.import_capture_layer(path, do_undo=False)
            elif requested_capture_identifier != current_capture_identifier:
                omni.kit.commands.execute(
                    self._SWITCH_CAPTURE_COMMAND_NAME,
                    new_capture_path=path,
                    context_name=self._context_name,
                )
        elif layer_type == _LayerType.replacement:
            self._replacement_core_setup.import_replacement_layer(path, use_existing_layer=existing_file)
        self._update_modding_button_state()

    def _on_open_workfile(self, path):
        return self.prompt_if_unsaved_project(lambda: self.__open_stage_and_load_layout(path), "changing project")

    def __open_stage_and_load_layout(self, path):
        project_path = Path(path)
        if not _ProjectWizardSchema.is_project_file_valid(
            project_path, {_ProjectWizardKeys.EXISTING_PROJECT.value: True}
        ):
            self.__show_project_open_wizard(project_path)
            return
        deps_directory = project_path.parent / _REMIX_DEPENDENCIES_FOLDER
        if not _ProjectWizardSchema.is_deps_directory_valid(deps_directory) and _should_confirm_link_path_replacement(
            deps_directory
        ):
            _show_invalid_deps_rebuild_dialog(deps_directory, partial(self.__show_project_open_wizard, project_path))
            return
        if not _ProjectWizardSchema.are_project_symlinks_valid(project_path):
            self.__show_project_open_wizard(project_path)
            return
        # Disable Opacity Micromaps before this project's capture is realized so it cannot fault/hang
        # the GPU on open. This MUST run before ``open_stage`` -- the renderer realizes the capture
        # during ``open_stage``, so the override cannot wait for a post-open (stage-opened) event.
        self._apply_capture_safe_mode(project_path)
        self.__set_stage_open_lighting_undo_disabled(True)
        omni.kit.window.file.open_stage(path)
        load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))

    def _on_save_as(self, on_save_done: Callable[[bool, str], None] = None):
        self._stage_core_setup.save_as(on_save_done=on_save_done)

    def _on_save(self, on_save_done: Callable[[bool, str], None] = None):
        self._stage_core_setup.save(on_save_done=on_save_done)

    def _on_unselect_all(self):
        self._context.get_selection().clear_selected_prim_paths()

    def _show_capture_swap_undo_dialog(self):
        if self._capture_swap_undo_dialog_open:
            return

        self._capture_swap_undo_dialog_open = True

        def _close_dialog(undo_capture_change: bool = False):
            self._capture_swap_undo_dialog_open = False
            if undo_capture_change:
                self._stage_core_setup.undo()

        _TrexMessageDialog(
            message="Undoing this action will change the loaded capture.\n\nDo you want to load the previous capture?",
            title="Undo Capture Change",
            ok_label="Load Capture",
            cancel_label="Cancel",
            ok_handler=lambda: _close_dialog(undo_capture_change=True),
            cancel_handler=_close_dialog,
            on_window_closed_fn=_close_dialog,
        )

    def _on_undo(self):
        if self._capture_swap_undo_dialog_open:
            return
        if omni.kit.undo.can_undo():
            undo_stack = list(omni.kit.undo.get_undo_stack())
            if undo_stack and undo_stack[-1].name == self._SWITCH_CAPTURE_COMMAND_NAME:
                self._show_capture_swap_undo_dialog()
                return
        self._stage_core_setup.undo()

    def _on_redo(self):
        self._stage_core_setup.redo()

    def _on_new_workfile(self):
        return self.prompt_if_unsaved_project(
            self.__create_stage_and_save_previous_identifier, "unloading the current stage"
        )

    def __create_stage_and_save_previous_identifier(self):
        ensure_future(self._context.close_stage_async())
        load_layout(_get_quicklayout_config(_LayoutFiles.HOME_PAGE))

    def __open_layout(self, x, y, b, m):
        if b != 0:
            return
        load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))

    def _on_stage_event(self, event):
        if event.type in {int(omni.usd.StageEventType.OPENED), int(omni.usd.StageEventType.CLOSING)}:
            asyncio.ensure_future(self._update_modding_button_state_deferred(event.type))

    async def _update_modding_button_state_deferred(self, event_type: int):
        await omni.kit.app.get_app().next_update_async()
        self._update_modding_button_state()
        if event_type == int(omni.usd.StageEventType.OPENED):
            self.__set_stage_open_lighting_undo_disabled(False)
            self._check_capture_on_open()

    def _check_capture_on_open(self):
        """Open the project wizard when a project is loaded with a missing capture layer."""
        project_layer = self._layer_manager.get_layer_of_type(_LayerType.workfile)
        capture_layer = self._layer_manager.get_layer_of_type(_LayerType.capture)
        if not project_layer or capture_layer:
            return
        if not project_layer.realPath:
            return
        project_path = Path(project_layer.realPath)
        deps_directory = project_path.parent / _REMIX_DEPENDENCIES_FOLDER
        deps_directory_invalid = not _ProjectWizardSchema.is_deps_directory_valid(deps_directory)
        if deps_directory_invalid and _should_confirm_link_path_replacement(deps_directory):
            _show_invalid_deps_rebuild_dialog(deps_directory, partial(self.__show_capture_repair_wizard, project_path))
            return
        if deps_directory_invalid:
            self.__show_capture_repair_wizard(project_path)
            return
        self.__show_capture_repair_wizard(project_path, deps_directory.resolve())

    def __show_project_open_wizard(self, project_path: Path):
        wizard = _get_wizard_instance(_WizardTypes.OPEN, self._context_name)
        wizard.set_payload({_ProjectWizardKeys.PROJECT_FILE.value: project_path})
        wizard.show_project_wizard(reset_page=True)

    def __show_capture_repair_wizard(self, project_path: Path, remix_directory: Path | None = None):
        wizard = _get_wizard_instance(_WizardTypes.OPEN, self._context_name)
        payload = {_ProjectWizardKeys.PROJECT_FILE.value: project_path}
        if remix_directory:
            payload[_ProjectWizardKeys.REMIX_DIRECTORY.value] = remix_directory
        wizard.set_payload(payload)
        wizard.show_capture_picker = True
        self._sub_wizard_completed = wizard.subscribe_wizard_completed(self._on_capture_repair_completed)
        wizard.show_project_wizard(reset_page=True)

    def _on_capture_repair_completed(self, payload):
        """Import the user-selected capture layer into the already-open stage without recording undo."""
        capture_file = payload.get(_ProjectWizardKeys.CAPTURE_FILE.value)
        if not capture_file:
            return
        project_file = payload.get(_ProjectWizardKeys.PROJECT_FILE.value)
        if not project_file:
            return
        capture_path = (
            Path(str(project_file)).parent
            / _REMIX_DEPENDENCIES_FOLDER
            / _REMIX_CAPTURE_FOLDER
            / Path(str(capture_file)).name
        )
        self._capture_core_setup.import_capture_layer(str(capture_path), do_undo=False)

    def _update_modding_button_state(self):
        if not self.__sub_sidebar_items:
            return
        stage = self._context.get_stage()
        if not stage:
            self.__sub_sidebar_items.set_enabled(False)
            return
        root_layer = stage.GetRootLayer()
        has_project = root_layer and not bool(root_layer.anonymous)
        self.__sub_sidebar_items.set_enabled(bool(has_project))

    # --- Capture GPU device-loss / hang safe mode ------------------------------------------------

    def _reassert_interval_seconds(self) -> float:
        """Resolve the periodic re-assert interval (seconds); falls back to the default."""
        value = carb.settings.get_settings().get(_SETTING_REASSERT_INTERVAL)
        try:
            return float(value) if value is not None else _DEFAULT_REASSERT_INTERVAL_SECONDS
        except (TypeError, ValueError):
            return _DEFAULT_REASSERT_INTERVAL_SECONDS

    def _push_stability_configvars(self):
        """Push the renderer overrides that keep a capture from faulting/hanging the GPU."""
        # graphicsPreset=Custom first so the Quality preset stops shadowing the User-layer writes,
        # then force ReSTIR GI (off the Neural Radiance Cache) and disable Opacity Micromaps.
        _set_hdremix_configvar(_RTX_OPTION_GRAPHICS_PRESET, _RTX_GRAPHICS_PRESET_CUSTOM)
        _set_hdremix_configvar(_RTX_OPTION_INTEGRATE_INDIRECT_MODE, _RTX_INTEGRATE_INDIRECT_MODE_RESTIR)
        _set_hdremix_configvar(_RTX_OPTION_OMM_ENABLE, _RTX_OMM_DISABLED)

    def _arm_safe_mode(self, source_path: str):
        """Disable Opacity Micromaps, remember the source, and start the periodic re-assert watchdog."""
        try:
            self._push_stability_configvars()
        except Exception as error:  # noqa: BLE001 - never break project open on a runtime hiccup
            carb.log_warn(f"Failed to disable Opacity Micromaps for '{source_path}': {error}")
            return
        self._safe_mode_capture_path = str(source_path).replace("\\", "/").lower()
        carb.log_info(
            f"Disabled Opacity Micromaps for capture project '{source_path}' (graphicsPreset=Custom, "
            "integrateIndirectMode=ReSTIR GI, opacityMicromap.enable=0) before stage realization to "
            "avoid a GPU device-loss/hang; re-asserting periodically."
        )
        self._start_reassert_watchdog()

    def _apply_capture_safe_mode(self, project_path: Path):
        """On project open: disable Opacity Micromaps before the capture is realized.

        StageCraft opens game-capture projects, and a dense capture's Opacity-Micromap build can
        fault/hang the GPU. Prim count does not reliably predict which captures do this, and OMM is
        only a render-time optimization (no effect on visuals, editing, or asset replacement), so --
        gated by a single toggle -- we disable OMM for any capture project rather than trying to
        guess which ones are dangerous.
        """
        if not carb.settings.get_settings().get(_SETTING_AUTO_SAFE_MODE):
            self._stop_reassert_watchdog()
            self._safe_mode_capture_path = None
            carb.log_info(
                f"Opacity Micromap auto-disable is off (autoDisableOpacityMicromaps=false); opening "
                f"'{project_path}' with full renderer settings."
            )
            return
        self._arm_safe_mode(str(project_path))

    def _apply_capture_safe_mode_on_switch(self, capture_path: str | None):
        """On capture switch: keep Opacity Micromaps disabled for the switched-to capture."""
        if not carb.settings.get_settings().get(_SETTING_AUTO_SAFE_MODE):
            return
        if self._safe_mode_capture_path is not None:
            # Safe mode already armed this session -- just re-assert the overrides.
            self._reassert_overrides_if_active()
            return
        self._arm_safe_mode(str(capture_path) if capture_path else "capture switch")

    def _reassert_overrides_if_active(self):
        """Re-push the overrides if safe mode is currently armed."""
        if self._safe_mode_capture_path is None:
            return
        try:
            self._push_stability_configvars()
        except Exception as error:  # noqa: BLE001 - never break on a runtime hiccup
            carb.log_warn(f"Failed to re-assert Opacity Micromap override: {error}")

    def _start_reassert_watchdog(self):
        """Periodically re-push the overrides so the capture's own preset cannot re-enable OMM.

        The pre-open push only covers the initial realization. When the capture finishes realizing,
        dxvk-remix applies the capture's own graphics preset, flipping ``graphicsPreset`` off Custom
        and re-enabling Opacity Micromaps + the Neural Radiance Cache integrator. The runtime does
        not mirror that into the ``/rtx/*`` carb nodes, so no settings callback fires; re-pushing the
        configvars on a short cadence corrects the drift before OMM baking can OOM and pin the GPU
        into the acceleration-structure rebuild that ends in a device loss.
        """
        interval = self._reassert_interval_seconds()
        if interval <= 0:
            return
        if self._reassert_watch_task is not None and not self._reassert_watch_task.done():
            return
        self._reassert_watch_task = ensure_future(self._reassert_watch_loop(interval))
        carb.log_info(
            f"Started capture stability watchdog (re-asserting renderer overrides every {interval:g}s so "
            "the loaded capture's preset cannot re-enable Opacity Micromaps mid-session)."
        )

    def _stop_reassert_watchdog(self):
        """Cancel the periodic re-assert loop (no-op if it was never started)."""
        if self._reassert_watch_task is not None and not self._reassert_watch_task.done():
            self._reassert_watch_task.cancel()
        self._reassert_watch_task = None

    async def _reassert_watch_loop(self, interval: float):
        """Re-assert the overrides every ``interval`` seconds while a capture stays loaded."""
        try:
            while self._safe_mode_capture_path is not None:
                await asyncio.sleep(interval)
                # The project may have been closed/swapped out while we slept.
                if self._safe_mode_capture_path is None:
                    break
                try:
                    self._push_stability_configvars()
                except Exception as error:  # noqa: BLE001 - a transient hiccup must not kill the loop
                    carb.log_warn(f"Periodic capture stability re-assert failed: {error}")
        except asyncio.CancelledError:
            pass

    def destroy(self):
        self._stop_reassert_watchdog()
        self.__set_stage_open_lighting_undo_disabled(False)
        self.__uninstall_stage_open_lighting_undo_patch()
        _reset_default_attrs(self)
