"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio

import carb
import omni.kit.app
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

_CONTEXT = "/exts/lightspeed.event.load_edit_target/context"


class EventLoadEditTargetCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(context_name)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "LoadEditTarget"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._stage_event_sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageEventListener"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._stage_event_sub = None

    def __on_stage_event(self, event):
        # Only restore when opening the project
        if event.type != int(omni.usd.StageEventType.OPENED):
            return

        asyncio.ensure_future(self.__load_edit_target_deferred())

    async def __load_edit_target_deferred(self):
        # If we don't wait 1 frame the edit target gets overridden
        await omni.kit.app.get_app().next_update_async()
        _layers.LayerUtils.restore_authoring_layer_from_custom_data(self._context.get_stage())

    def destroy(self):
        _reset_default_attrs(self)
