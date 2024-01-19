"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Any, Callable

from omni.kit.viewport.menubar.render import SingleRenderMenuItemBase


def lss_single_render_menu_item(*args, lss_option_clicked: Callable[[str, str], Any] = None, **kwargs):
    class LssSingleRenderMenuItem(SingleRenderMenuItemBase):

        # Note: This cannot currently be triggered since we skip building the menu button below
        def _option_clicked(self):
            lss_option_clicked(self.engine_name, self.hd_renderer.pluginID)

        def _build_menuitem_widgets(self):
            # skip building menu button for now, because we won't show anything.
            pass

    return LssSingleRenderMenuItem(*args, **kwargs)
