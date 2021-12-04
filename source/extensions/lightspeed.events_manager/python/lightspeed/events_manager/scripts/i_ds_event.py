"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import abc

import six


@six.add_metaclass(abc.ABCMeta)
class ILSSEvent:
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the event"""
        return ""

    def install(self):
        self._install()

    @abc.abstractmethod
    def _install(self):
        """Function that will create the behavior"""
        pass

    def uninstall(self):
        self._uninstall()

    @abc.abstractmethod
    def _uninstall(self):
        """Function that will delete the behavior"""
        pass
