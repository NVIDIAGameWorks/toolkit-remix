"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.layout.stagecraft import get_instance as _get_layout_instance
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCoreSetup
from lightspeed.trex.stage.core.shared import Setup as _StageCoreSetup
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self):
        self._default_attr = {
            "_layout_instance": None,
            "_sub_new_work_file_clicked": None,
            "_stage_core_setup": None,
            "_capture_core_setup": None,
            "_replacement_core_setup": None,
            "_sub_import_capture_layer": None,
            "_sub_import_replacement_layer": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = _trex_contexts_instance().get_context(_TrexContexts.STAGE_CRAFT)
        self._layout_instance = _get_layout_instance()
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

    def _on_import_capture_layer(self, path: str):
        self._capture_core_setup.import_capture_layer(path)

    def _on_import_replacement_layer(self, path: str, use_existing_layer: bool = True):
        self._replacement_core_setup.import_replacement_layer(path, use_existing_layer=use_existing_layer)

    def _on_new_work_file_clicked(self):
        self._stage_core_setup.create_new_work_file()

    def destroy(self):
        _reset_default_attrs(self)
