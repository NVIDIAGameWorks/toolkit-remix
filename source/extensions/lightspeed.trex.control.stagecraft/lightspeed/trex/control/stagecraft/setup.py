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
from functools import partial
from pathlib import Path
from collections.abc import Callable

import carb
import lightspeed.trex.sidebar as sidebar
import omni.kit.app
import omni.ui
import omni.usd
from lightspeed.common.constants import GlobalEventNames
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
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
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

_TREX_IGNORE_UNSAVED_STAGE_ON_EXIT = "/app/file/trexIgnoreUnsavedOnExit"
_DEFAULT_LAYOUT = "/app/trex/default_layout"


class Setup:
    def __init__(self):
        self._default_attr = {
            "_sub_wizard_completed": None,
            "_stage_core_setup": None,
            "_capture_core_setup": None,
            "_replacement_core_setup": None,
            "_sub_import_capture_layer": None,
            "_sub_import_replacement_layer": None,
            "_sub_open_workfile": None,
            "_layer_manager": None,
            "_previous_root_layer_identifier": None,
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
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = _TrexContexts.STAGE_CRAFT.value
        self._context = _trex_contexts_instance().get_usd_context(_TrexContexts.STAGE_CRAFT)
        self._layer_manager = _LayerManagerCore(context_name=_TrexContexts.STAGE_CRAFT.value)
        self._previous_root_layer_identifier = None
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
            load_layout(_get_quicklayout_config(_LayoutFiles.HOME_PAGE))

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

        layer_capture = self._layer_manager.get_layer(_LayerType.capture)
        layer_replacement = self._layer_manager.get_layer(_LayerType.replacement)
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
                    disabled_tooltip="Modding (Only available if there are projects open).",
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
            self._capture_core_setup.import_capture_layer(path)
        elif layer_type == _LayerType.replacement:
            self._replacement_core_setup.import_replacement_layer(path, use_existing_layer=existing_file)
        self._update_modding_button_state()

    def _on_open_workfile(self, path):
        return self.prompt_if_unsaved_project(
            lambda: self.__open_stage_and_save_previous_identifier(path), "changing project"
        )

    def __open_stage_and_save_previous_identifier(self, path):
        if not _ProjectWizardSchema.is_project_file_valid(
            Path(path), {_ProjectWizardKeys.EXISTING_PROJECT.value: True}
        ) or not _ProjectWizardSchema.are_project_symlinks_valid(Path(path)):
            wizard = _get_wizard_instance(_WizardTypes.OPEN, self._context_name)
            wizard.set_payload({_ProjectWizardKeys.PROJECT_FILE.value: Path(path)})
            wizard.show_project_wizard(reset_page=True)
            return
        self._previous_root_layer_identifier = self._layer_manager.open_stage(path)
        load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))

    def _on_save_as(self, on_save_done: Callable[[bool, str], None] = None):
        self._stage_core_setup.save_as(on_save_done=on_save_done)

    def _on_save(self, on_save_done: Callable[[bool, str], None] = None):
        self._stage_core_setup.save(on_save_done=on_save_done)

    def _on_unselect_all(self):
        self._context.get_selection().clear_selected_prim_paths()

    def _on_undo(self):
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
        if event.type in [int(omni.usd.StageEventType.OPENED), int(omni.usd.StageEventType.CLOSING)]:
            asyncio.ensure_future(self._update_modding_button_state_deferred())

    async def _update_modding_button_state_deferred(self):
        await omni.kit.app.get_app().next_update_async()
        self._update_modding_button_state()

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

    def destroy(self):
        _reset_default_attrs(self)
