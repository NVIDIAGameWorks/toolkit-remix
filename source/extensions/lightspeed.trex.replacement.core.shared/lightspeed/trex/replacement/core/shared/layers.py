import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType as _LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class AssetReplacementLayersCore:
    def __init__(self, context_name: str = ""):
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_layer_manager": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(self._context_name)
        self._layer_manager = _LayerManagerCore(self._context_name)

    @property
    def _layer_replacement(self):
        return self._layer_manager.get_layer(_LayerType.replacement)

    @property
    def _layer_capture(self):
        return self._layer_manager.get_layer(_LayerType.capture)

    @property
    def _layer_root(self):
        stage = self._context.get_stage()
        return stage.GetRootLayer() if stage else None

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

    def get_layers_exclude_add_child(self):
        return [
            layer.identifier
            for layer in [
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def destroy(self):
        _reset_default_attrs(self)
