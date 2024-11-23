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

__all__ = ["PyCharmDebuggerCore"]

import sys
from pathlib import Path

import carb.settings
from omni.flux.utils.common import reset_default_attrs


class PyCharmDebuggerCore:
    _PYCHARM_SETTINGS = "/exts/omni.flux.debug.pycharm"

    def __init__(self, ext_name: str):
        self._default_attr = {
            "_ext_name": None,
            "_settings": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._ext_name = ext_name
        self._settings = None

    def setup(self):
        self._settings = carb.settings.get_settings().get(self._PYCHARM_SETTINGS)
        try:
            self._setup_pydevd_module()
        except RuntimeError as e:
            raise RuntimeError(f"{self._ext_name} Could not setup pydevd module") from e
        try:
            import pydevd_pycharm

            pydevd_pycharm.settrace(
                self._settings["host"],
                port=self._settings["port"],
                suspend=self._settings["suspend_on_start"],
                stdoutToServer=True,
                stderrToServer=True,
            )
        except ModuleNotFoundError as e:
            raise RuntimeError(f"{self._ext_name} pydevd module was configured but could not be imported") from e
        except ConnectionRefusedError as e:
            raise RuntimeError(
                f"{self._ext_name} Could not connect to PyCharm at {self._settings['host']}:{self._settings['port']}"
            ) from e

        print(f"{self._ext_name} Connected to PyCharm at {self._settings['host']}:{self._settings['port']}")

    def _setup_pydevd_module(self):
        if self._settings["pycharm_location"]:
            pycharm_path = Path(self._settings["pycharm_location"]).resolve()
            pydev_location = pycharm_path / "plugins/python/helpers/pydev"
            if not pydev_location.exists():
                pydev_location = pycharm_path / "plugins/python-ce/helpers/pydev"
            if not pydev_location.exists():
                raise FileNotFoundError(f"{self._ext_name} Could not find pydev folder in {pycharm_path}")
            sys.path.append(pydev_location.resolve().as_posix())
        elif self._settings["pip_install_pydevd"]:
            try:
                import omni.kit.pipapi

                pydevd_version = self._settings.get("pydevd_version", "243.22562.23")
                omni.kit.pipapi.install(
                    package=f"pydevd-pycharm~={pydevd_version}", module="pydevd_pycharm", ignore_import_check=False
                )
            except Exception as e:
                raise RuntimeError(f"{self._ext_name} Could not install pydevd with pip: {e}") from e
        else:
            raise RuntimeError(
                f"{self._ext_name} Extension enabled but neither PyCharm location nor pip install was configured"
            )

    def destroy(self):
        reset_default_attrs(self)
