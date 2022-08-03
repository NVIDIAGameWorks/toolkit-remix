"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Callable

from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.layout.stagecraft import get_instance as _get_layout_instance
from lightspeed.trex.menu.workfile import get_instance as _get_menu_workfile_instance
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
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = _trex_contexts_instance().get_context(_TrexContexts.STAGE_CRAFT)
        self._layer_manager = _LayerManagerCore(context=self._context)
        self._layout_instance = _get_layout_instance()
        self._menu_workfile_instance = _get_menu_workfile_instance()
        self._stage_core_setup = _StageCoreSetup(self._context)
        self._capture_core_setup = _CaptureCoreSetup(self._context)
        self._replacement_core_setup = _ReplacementCoreSetup(self._context)
        self._sub_new_work_file_clicked = self._layout_instance.subscribe_new_work_file_clicked(
            self._on_new_work_file_clicked
        )
        self._sub_import_capture_layer = self._layout_instance.subscribe_import_capture_layer(
            self._on_import_capture_layer
        )
        self._sub_import_replacement_layer = self._layout_instance.subscribe_import_replacement_layer(
            self._on_import_replacement_layer
        )
        self._sub_open_workfile = self._layout_instance.subscribe_open_work_file(self._on_open_workfile)
        self._sub_menu_workfile_save = self._menu_workfile_instance.subscribe_save(self._on_save)
        self._sub_menu_workfile_save_as = self._menu_workfile_instance.subscribe_save_as(self._on_save_as)

    def _on_import_capture_layer(self, path: str):
        self._capture_core_setup.import_capture_layer(path)

    def _on_import_replacement_layer(self, path: str, use_existing_layer: bool = True):
        self._replacement_core_setup.import_replacement_layer(path, use_existing_layer=use_existing_layer)

    def _on_new_work_file_clicked(self):
        self._stage_core_setup.create_new_work_file()

    def _on_open_workfile(self, path):
        def open_file(path):
            self._stage_core_setup.open_stage(path)

        def on_saved_okay_clicked(dialog: _TrexMessageDialog):
            dialog.hide()
            open_file(path)

        def on_saved_cancel_clicked(dialog: _TrexMessageDialog):
            dialog.hide()

        def on_save(result, error):
            if not result or error:
                dialog = _TrexMessageDialog(
                    width=600,
                    message="Error saving",
                    disable_cancel_button=True,
                )
                dialog.show()
                return
            message = f"Are you sure you want to open this workfile?\n{path}"

            dialog = _TrexMessageDialog(
                width=600,
                message=message,
                ok_handler=on_saved_okay_clicked,
                cancel_handler=on_saved_cancel_clicked,
                ok_label="Yes",
                disable_cancel_button=False,
            )
            dialog.show()

        def on_okay_clicked(dialog: _TrexMessageDialog):
            dialog.hide()
            self._on_save_as(on_save_done=on_save)

        def on_cancel_clicked(dialog: _TrexMessageDialog):
            dialog.hide()
            on_save(True, "")

        layer_capture = self._layer_manager.get_layer(_LayerType.capture)
        layer_replacement = self._layer_manager.get_layer(_LayerType.replacement)
        if self._context.has_pending_edit() and layer_capture and layer_replacement:
            message = "There is some pending edits on your current stage.\nDo you want to save your stage before"

            dialog = _TrexMessageDialog(
                width=600,
                message=message,
                ok_handler=on_okay_clicked,
                cancel_handler=on_cancel_clicked,
                ok_label="Yes",
                disable_cancel_button=False,
            )
            dialog.show()
        else:
            open_file(path)

    def _on_save(self):
        self._stage_core_setup.save()

    def _on_save_as(self, on_save_done: Callable[[bool, str], None] = None):
        self._stage_core_setup.save_as(on_save_done=on_save_done)

    def destroy(self):
        _reset_default_attrs(self)
