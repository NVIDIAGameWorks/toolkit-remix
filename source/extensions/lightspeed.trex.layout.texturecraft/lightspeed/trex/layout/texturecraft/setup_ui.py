"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from lightspeed.common.constants import TEXTURE_SCHEMA_PATHS as _TEXTURE_SCHEMA_PATHS
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared.mass_ingestion import SetupUI as _IngestionLayout


class SetupUI(_IngestionLayout):
    def __init__(self, ext_id):
        super().__init__(ext_id, _TEXTURE_SCHEMA_PATHS, context=TrexContexts.TEXTURE_CRAFT)

    @property
    def button_name(self) -> str:
        return "Texture AI"

    @property
    def button_priority(self) -> int:
        return 20
