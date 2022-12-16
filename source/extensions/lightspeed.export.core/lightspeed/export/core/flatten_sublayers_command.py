"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Union

import omni
from omni.kit.usd.layers import FlattenLayersCommand, MergeLayersCommand
from pxr import Sdf


class FlattenSubLayersCommand(FlattenLayersCommand):
    """Flatten Sublayers undoable **Command**."""

    def __init__(self, usd_context: Union[str, omni.usd.UsdContext], layer_to_flatten: Sdf.Layer):
        """Constructor.

        Keyword Arguments:
            usd_context (Union[str, omni.usd.UsdContext]): Usd context name or instance. It uses default context if
                                                           it's empty.

            layer_to_flatten (str): The layer that is the root of the tree oflayers which will be flattened into a
                                    single layer.
        """
        self._layer_to_flatten = layer_to_flatten
        super().__init__(usd_context)
        self._merges = []

    def _get_sublayers_from_strongest_to_weakest(self):
        root_layer = self._layer_to_flatten
        all_layers = []
        current_subtree_stack = []
        self._traverse(all_layers, None, root_layer, root_layer.identifier, current_subtree_stack)

        return all_layers

    def do_impl(self):
        all_sublayers = self._get_sublayers_from_strongest_to_weakest()
        for parent, child in all_sublayers:
            if child != self._layer_to_flatten.identifier:
                merge = MergeLayersCommand(
                    None,
                    self._layer_to_flatten.identifier,
                    parent,
                    child,
                    False,
                )
                merge.do_impl()
                self._merges.append(merge)


omni.kit.commands.register(FlattenSubLayersCommand)
