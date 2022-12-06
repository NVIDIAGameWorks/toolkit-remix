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


class LayerItem:
    @property
    @abc.abstractmethod
    def visible(self):
        pass

    @visible.setter
    @abc.abstractmethod
    def visible(self, value):
        pass

    @property
    @abc.abstractmethod
    def name(self):
        pass

    @property
    @abc.abstractmethod
    def layers(self):
        pass

    @property
    @abc.abstractmethod
    def categories(self):
        pass

    @abc.abstractmethod
    def destroy(self):
        # Respond to destroy, but since this doesn't own the underlying viewport, don't forward to it
        pass
