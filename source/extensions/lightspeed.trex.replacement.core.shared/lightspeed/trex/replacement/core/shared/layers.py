import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType as _LayerType
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class AssetReplacementLayersCore:
    def __init__(self, context_name: str = ""):
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage": None,
            "_layer_manager": None,
            "_layer_replacement": None,
            "_layer_capture": None,
            "_layer_root": None,
            "_stage_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self.__on_stage_event = _Event()

        self._context_name = context_name
        self._context = omni.usd.get_context(self._context_name)
        self._stage = self._context.get_stage()
        self._layer_manager = _LayerManagerCore(self._context_name)

        self._stage_event_sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="Stage Events"
        )

        self.__get_default_layers()

    def get_layers_exclude_remove(self):
        return [
            layer.identifier
            for layer in [
                self._layer_replacement,
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_lock(self):
        return [
            layer.identifier
            for layer in [
                self._layer_replacement,
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_mute(self):
        return [
            layer.identifier
            for layer in [
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_edit_target(self):
        return [
            layer.identifier
            for layer in [
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def _on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
        ]:
            self._stage = self._context.get_stage()
            self.__get_default_layers()
            self._stage_event()

    def __get_default_layers(self):
        self._layer_replacement = self._layer_manager.get_layer(_LayerType.replacement)
        self._layer_capture = self._layer_manager.get_layer(_LayerType.capture)

        self._layer_root = None
        if self._stage is not None:
            self._layer_root = self._stage.GetRootLayer()

    def _stage_event(self):
        """Call the event object that has the list of functions"""
        self.__on_stage_event()

    def subscribe_stage_event(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_stage_event, func)

    def destroy(self):
        _reset_default_attrs(self)
