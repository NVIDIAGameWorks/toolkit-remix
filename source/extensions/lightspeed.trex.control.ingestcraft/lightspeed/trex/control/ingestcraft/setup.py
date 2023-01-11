"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.layout.ingestcraft import get_instance as _get_layout_instance
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context_name = _TrexContexts.INGEST_CRAFT.value
        self._context = _trex_contexts_instance().get_context(_TrexContexts.INGEST_CRAFT)
        self._layout_instance = _get_layout_instance()

        self._context.new_stage()  # TODO: to remove when we open a stage

    def destroy(self):
        _reset_default_attrs(self)
