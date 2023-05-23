"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import abc
import typing

from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.ui import scene as _sc

if typing.TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI


class IManipulator:
    def __init__(self, viewport_api: "ViewportAPI"):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__viewport_api = viewport_api
        self.__manipulator = self._create_manipulator()
        if self.__manipulator:
            self.__model_changed_sub = self.__manipulator.model.subscribe_item_changed_fn(self._model_changed)  # noqa

    @property
    def viewport_api(self):
        return self.__viewport_api

    @abc.abstractmethod
    def _create_manipulator(self) -> _sc.Manipulator:
        pass

    def manipulator(self):
        return self.__manipulator

    @property
    @abc.abstractmethod
    def categories(self):
        return []

    @property
    @abc.abstractmethod
    def name(self):
        return ""

    @property
    def visible(self):
        return self.__manipulator.visible

    @visible.setter
    def visible(self, value):
        self.__manipulator.visible = bool(value)

    @abc.abstractmethod
    def _model_changed(self, model, item):
        pass

    def destroy(self):
        self.__model_changed_sub = None  # noqa
        self.__manipulator = None
        self.__viewport_api = None
        if self._default_attr:
            _reset_default_attrs(self)
