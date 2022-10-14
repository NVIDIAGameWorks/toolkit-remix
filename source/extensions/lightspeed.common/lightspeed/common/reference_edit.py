"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.usd
from pxr import Usd


class ReferenceEdit:
    """Utility class to allow editing the source USD of a referenced object.
    The source USD will be saved when the `with` block exits.

    Args:
        prim (Usd.Prim): The highest level prim being edited

    Example:
        >>> with ReferenceEdit(stage, prim):
        >>>     # edit prim, including any descendents of the prim.
    """

    def __init__(self, prim):
        self._prim = prim
        self._stage = omni.usd.get_context().get_stage()
        self._default_edit_target = self._stage.GetEditTarget()
        self._refNode = None

    def __enter__(self):
        if self._prim.GetPrimIndex().rootNode.children:
            self._refNode = self._prim.GetPrimIndex().rootNode.children[0]
            # if a prim's nested under several references, chase it all the way to the bottom.
            while self._refNode.children:
                self._refNode = self._refNode.children[0]

            self._stage.SetEditTarget(Usd.EditTarget(self._refNode.layerStack.layers[0], self._refNode))
        else:
            self._stage.SetEditTarget(self._default_edit_target)

    def __exit__(self, e_type, value, traceback):
        if self._refNode:
            self._refNode.layerStack.layers[0].Save()
        self._stage.SetEditTarget(self._default_edit_target)
