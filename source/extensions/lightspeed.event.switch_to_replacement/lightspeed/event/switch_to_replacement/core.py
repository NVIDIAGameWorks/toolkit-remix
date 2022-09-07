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
from omni.kit.notification_manager import NotificationStatus, post_notification
from omni.kit.usd.layers import LayerEventType, get_layer_event_payload, get_layers
from pxr import Sdf


class SwitchToReplacementCore(ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_subscription": None, "_layer_manager": None, "_layer_sub": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context()
        self._layer_manager = LayerManagerCore()

    @property
    def name(self) -> str:
        """Name of the event"""
        return "Switch to Replacement"

    def _install(self):
        """Function that will create the behavior"""
        self._subscription = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_save_open_event, name="Recent file saved"
        )
        layers = get_layers()
        event_stream = layers.get_event_stream()
        self._layer_sub = event_stream.create_subscription_to_pop(self._on_layer_event, name="layer events")

    def _on_layer_event(self, event: carb.events.IEvent):
        temp = get_layer_event_payload(event)
        if temp.event_type in [
            LayerEventType.EDIT_TARGET_CHANGED,
            LayerEventType.SUBLAYERS_CHANGED,
            LayerEventType.LOCK_STATE_CHANGED,
            LayerEventType.EDIT_MODE_CHANGED,
        ]:
            self.check_current_edit_layer()

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._subscription = None
        self._layer_sub = None

    def __on_save_open_event(self, event):
        if event.type in [int(omni.usd.StageEventType.SAVED), int(omni.usd.StageEventType.OPENED)]:
            self.check_current_edit_layer()

    def check_current_edit_layer(self):
        def get_sublayer(layer):
            result = []
            for sublayer in layer.subLayerPaths:
                sublayer_identifier = layer.ComputeAbsolutePath(sublayer)
                result.append(sublayer_identifier)
                sublayer = Sdf.Find(sublayer_identifier)
                result.extend(get_sublayer(sublayer))
            return result

        layer_replacement = self._layer_manager.get_layer(LayerType.replacement)
        # we only save stage that have a replacement layer
        if not layer_replacement:
            # this can be ok when the user works on asset(s)
            # checking is there is a capture layer. If there is one, we need a replacement layer. If not, we don't care
            layer_capture = self._layer_manager.get_layer(LayerType.capture)
            if layer_capture:
                message = "Can't find the replacement layer in the current stage"
                post_notification(message, hide_after_timeout=False, status=NotificationStatus.WARNING)
                carb.log_verbose(message)
                return
            return
        stage = self._context.get_stage()
        default_edit_target = stage.GetEditTarget().GetLayer()
        valid_layer_paths = [layer_replacement.identifier]
        valid_layer_paths.extend(get_sublayer(layer_replacement))
        # if the current edit target is not part of the valid layers, switch it to the replacement layer
        if default_edit_target.identifier not in valid_layer_paths:
            message = "Current edit layer is not valid. Switching to the replacement/mod layer"
            carb.log_warn(message)
            post_notification(message, hide_after_timeout=False, status=NotificationStatus.WARNING)
            stage.SetEditTarget(layer_replacement)

        # check if the replacement/mod layer is locked or not
        layer_is_writable = omni.usd.is_layer_writable(layer_replacement.identifier)
        layer_is_locked = omni.usd.is_layer_locked(self._context, layer_replacement.identifier)
        if not layer_is_writable or layer_is_locked:
            message = "Current replacement/mod layer is locked/not writable"
            carb.log_warn(message)
            post_notification(message, hide_after_timeout=False, status=NotificationStatus.WARNING)

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
