"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import omni.client
import omni.usd
from lightspeed.events_manager.i_ds_event import ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore, LayerType


class EventLayersCleanupCore(ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_subscription": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context()
        self.__layer_manager = LayerManagerCore()

    @property
    def name(self) -> str:
        """Name of the event"""
        return "LayersCleanup"

    def _install(self):
        """Function that will create the behavior"""
        self._subscription = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_load_event, name="Recent file loaded"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._subscription = None

    def __on_load_event(self, event):
        if event.type in [int(omni.usd.StageEventType.OPENED)]:
            layer_replacement = self.__layer_manager.get_layer(LayerType.replacement)
            # we only save stage that have a replacement layer
            if not layer_replacement:
                carb.log_verbose("Can't find the replacement layer in the current stage")
                return
            layer_replacement.ClearTimeCodesPerSecond()
            layer_replacement.ClearStartTimeCode()
            layer_replacement.ClearEndTimeCode()

    def destroy(self):
        for attr, value in self.default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)
