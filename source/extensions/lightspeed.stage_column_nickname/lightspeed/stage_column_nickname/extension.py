"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ext
from omni.kit.widget.stage.stage_column_delegate_registry import StageColumnDelegateRegistry

from .nickname_delegate import NicknameStageColumnDelegate


class StageNicknameWidgetExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("booting up!")
        self._variant_column_sub = StageColumnDelegateRegistry().register_column_delegate(
            "Nickname", NicknameStageColumnDelegate
        )

    def on_shutdown(self):
        print("Shutting Down!")
