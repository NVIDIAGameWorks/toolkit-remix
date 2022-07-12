# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import carb
import carb.settings
import omni.ext
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts

from .setup_ui import SetupUI

_DEFAULT_LAYOUT_EXTENSION = "/app/trex/default_layout_extension"
_SETUP_INSTANCE = None


def get_instance():
    return _SETUP_INSTANCE


class TextureCraftLayoutExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.layout.texturecraft] Startup")
        # create the TextureCraft configurator context
        trex_contexts_instance().create_context(TrexContexts.TEXTURE_CRAFT)

        _SETUP_INSTANCE = SetupUI()
        settings = carb.settings.get_settings()
        default_layout = settings.get(_DEFAULT_LAYOUT_EXTENSION)
        if (default_layout and ext_id.startswith(default_layout)) or not default_layout:
            _SETUP_INSTANCE.create_layout()

    def on_shutdown(self):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.layout.texturecraft] Shutdown")
        _SETUP_INSTANCE.destroy()
        _SETUP_INSTANCE = None
