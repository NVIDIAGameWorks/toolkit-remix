"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from functools import partial
from typing import Callable

from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.layout.stagecraft import get_instance as _get_layout_instance
from lightspeed.trex.menu.workfile import get_instance as _get_menu_workfile_instance
from lightspeed.trex.project_wizard.window import ProjectWizardWindow as _ProjectWizardWindow
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCoreSetup
from lightspeed.trex.stage.core.shared import Setup as _StageCoreSetup
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self):
        self._default_attr = {
            "_sub_new_work_file_clicked": None,
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
            "_sub_key_undo": None,
            "_sub_key_redo": None,
            "_sub_key_save": None,
            "_sub_key_save_as": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = _TrexContexts.STAGE_CRAFT.value
        self._context = _trex_contexts_instance().get_context(_TrexContexts.STAGE_CRAFT)
        self._layer_manager = _LayerManagerCore(context_name=_TrexContexts.STAGE_CRAFT.value)
        self._layout_instance = _get_layout_instance()
        self._menu_workfile_instance = _get_menu_workfile_instance()
        self._stage_core_setup = _StageCoreSetup(self._context_name)
        self._capture_core_setup = _CaptureCoreSetup(self._context_name)
        self._replacement_core_setup = _ReplacementCoreSetup(self._context_name)
        self._wizard_window = _ProjectWizardWindow(self._context_name)

        self._sub_new_work_file_clicked = self._layout_instance.subscribe_new_work_file_clicked(
            self._wizard_window.show_project_wizard
        )
        self._sub_import_capture_layer = self._layout_instance.subscribe_import_capture_layer(
            self._on_import_capture_layer
        )
        self._sub_import_replacement_layer = self._layout_instance.subscribe_import_replacement_layer(
            self._on_import_replacement_layer
        )
        self._sub_open_workfile = self._layout_instance.subscribe_open_work_file(self._on_open_workfile)
        self._sub_key_undo = self._layout_instance.subscribe_ctrl_z_released(self._on_undo)
        self._sub_key_redo = self._layout_instance.subscribe_ctrl_y_released(self._on_redo)
        self._sub_key_save = self._layout_instance.subscribe_ctrl_s_released(self._on_save)
        self._sub_key_save_as = self._layout_instance.subscribe_ctrl_shift_s_released(self._on_save_as)

        self._sub_menu_workfile_save = self._menu_workfile_instance.subscribe_save(self._on_save)
        self._sub_menu_workfile_save_as = self._menu_workfile_instance.subscribe_save_as(self._on_save_as)
        self._sub_menu_workfile_undo = self._menu_workfile_instance.subscribe_undo(self._on_undo)
        self._sub_menu_workfile_redo = self._menu_workfile_instance.subscribe_redo(self._on_redo)

    def _on_import_capture_layer(self, path: str):
        self._capture_core_setup.import_capture_layer(path)

    def _on_import_replacement_layer(self, path: str, use_existing_layer: bool = True):
        self._replacement_core_setup.import_replacement_layer(path, use_existing_layer=use_existing_layer)

    def _on_open_workfile(self, path):
        def on_save(result, error):
            if not result or error:
                _TrexMessageDialog(
                    message="An error occurred while saving the workfile.",
                    disable_cancel_button=True,
                )
                return

            _TrexMessageDialog(
                message=f"Are you sure you want to open this workfile?\n\n{path}",
                ok_handler=partial(self._stage_core_setup.open_stage, path),
                ok_label="Open",
            )

        layer_capture = self._layer_manager.get_layer(_LayerType.capture)
        layer_replacement = self._layer_manager.get_layer(_LayerType.replacement)
        if self._context.has_pending_edit() and layer_capture and layer_replacement:
            _TrexMessageDialog(
                message="There are some pending edits in your current stage.\n\n"
                "Do you want to save your change before changing workfile?",
                ok_handler=partial(self._on_save_as, on_save_done=on_save),
                cancel_handler=partial(on_save, True, ""),
                ok_label="Save",
                cancel_label="Discard",
            )
        else:
            self._stage_core_setup.open_stage(path)

    def _on_save_as(self, on_save_done: Callable[[bool, str], None] = None):
        self._stage_core_setup.save_as(on_save_done=on_save_done)

    def _on_save(self):
        self._stage_core_setup.save()

    def _on_undo(self):
        self._stage_core_setup.undo()

    def _on_redo(self):
        self._stage_core_setup.redo()

    def destroy(self):
        _reset_default_attrs(self)
