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
from lightspeed.events_manager.scripts.i_ds_event import ILSSEvent
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType
from lightspeed.layer_manager.scripts.layers.replacement import LSS_LAYER_GAME_NAME

from .recent_saved_file_utils import RecentSavedFile


class EventSaveRecentCore(ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_subscription": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__rencent_saved_file = RecentSavedFile()
        self._context = omni.usd.get_context()
        self.__layer_manager = LayerManagerCore()

    @property
    def name(self) -> str:
        """Name of the event"""
        return "SaveRecent"

    def _install(self):
        """Function that will create the behavior"""
        self._subscription = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_save_event, name="Recent file saved"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._subscription = None

    def __on_save_event(self, event):
        if event.type == int(omni.usd.StageEventType.SAVED):
            layer_capture = self.__layer_manager.get_layer(LayerType.capture)
            # we only save stage that have a capture layer
            if not layer_capture:
                carb.log_verbose("Can't find the capture layer in the current stage")
            layer_replacement = self.__layer_manager.get_layer(LayerType.replacement)
            # we only save stage that have a replacement layer
            if not layer_replacement:
                carb.log_verbose("Can't find the replacement layer in the current stage")
                return
            path = self._context.get_stage_url()
            self.__rencent_saved_file.append_path_to_recent_file(
                omni.client.normalize_url(path),
                layer_replacement.customLayerData.get(LSS_LAYER_GAME_NAME),
                omni.client.normalize_url(layer_capture.realPath),
            )

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
