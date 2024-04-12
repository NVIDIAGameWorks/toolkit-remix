"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
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
