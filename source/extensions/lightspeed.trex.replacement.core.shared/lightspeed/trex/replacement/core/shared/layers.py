from typing import List, Optional

import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType as _LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf


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
    def _layer_replacement(self) -> Optional[Sdf.Layer]:
        return self._layer_manager.get_layer(_LayerType.replacement)

    @property
    def _layer_capture(self) -> Optional[Sdf.Layer]:
        return self._layer_manager.get_layer(_LayerType.capture)

    @property
    def _layer_root(self) -> Optional[Sdf.Layer]:
        stage = self._context.get_stage()
        return stage.GetRootLayer() if stage else None

    def get_layers_exclude_remove(self) -> List[str]:
        return [
            layer.identifier
            for layer in [
                self._layer_replacement,
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_lock(self) -> List[str]:
        return [
            layer.identifier
            for layer in [
                self._layer_replacement,
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_mute(self) -> List[str]:
        return [
            layer.identifier
            for layer in [
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_edit_target(self) -> List[str]:
        # Only allow the mod layer and its sub-layers to be set as edit targets
        def get_layer_paths_recursive(layer: Sdf.Layer) -> List[str]:
            sublayers = []
            sublayers.append(layer.identifier)
            for sublayer in layer.subLayerPaths:
                sublayers.extend(get_layer_paths_recursive(Sdf.Layer.FindOrOpenRelativeToLayer(layer, sublayer)))
            return sublayers

        mod_layers = get_layer_paths_recursive(self._layer_replacement)
        layer_stack = self._context.get_stage().GetLayerStack(includeSessionLayers=False)
        return [layer.identifier for layer in layer_stack if layer.identifier not in mod_layers]

    def get_layers_exclude_add_child(self) -> List[str]:
        return [
            layer.identifier
            for layer in [
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def get_layers_exclude_move(self) -> List[str]:
        return [
            layer.identifier
            for layer in [
                self._layer_replacement,
                self._layer_capture,
                self._layer_root,
            ]
            if layer is not None
        ]

    def destroy(self):
        _reset_default_attrs(self)
