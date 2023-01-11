"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from enum import Enum
from typing import List

import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Contexts(Enum):
    INGEST_CRAFT = "ingestcraft"
    TEXTURE_CRAFT = "texturecraft"
    # STAGE_CRAFT = "stagecraft"
    STAGE_CRAFT = ""  # TODO: wait for OM-77651


class _Setup:
    def __init__(self):
        self._default_attr = {"_usd_contexts": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._usd_contexts = []

    def create_context(self, usd_context_name: Contexts) -> omni.usd.UsdContext:
        usd_context = omni.usd.get_context(usd_context_name.value)
        if not usd_context:
            usd_context = omni.usd.create_context(usd_context_name.value)
            self._usd_contexts.append(usd_context)
        return usd_context

    def get_contexts(self) -> List[omni.usd.UsdContext]:
        return self._usd_contexts

    def get_context(
        self, usd_context_name: Contexts, create_if_not_exist: bool = True, do_raise: bool = True
    ) -> omni.usd.UsdContext:
        usd_context = omni.usd.get_context(usd_context_name.value)
        if not usd_context and not create_if_not_exist and do_raise:
            raise ValueError(f"Context {usd_context_name.value} was never created")
        if not usd_context and create_if_not_exist:
            usd_context = self.create_context(usd_context_name)
        return usd_context  # noqa R504

    def destroy(self):
        for context in Contexts:
            if self.get_context(context, create_if_not_exist=False, do_raise=False):
                omni.usd.destroy_context(context.value)
        _reset_default_attrs(self)


def create_instance() -> _Setup:
    return _Setup()
