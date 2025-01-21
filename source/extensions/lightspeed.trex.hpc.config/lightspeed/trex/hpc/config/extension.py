# Copyright (c) 2021-2024 Kuonirad RTX-Remix-Enhancements Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import omni.ext
import omni.kit.commands
import carb.settings

class HpcConfigExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._settings = carb.settings.get_settings()
        self._menu_path = f"Window/RTX Remix/HPC Configuration"
        
        # Register configuration options
        self._settings.set_default("/rtx/hpc/enablePipeline", True)
        self._settings.set_default("/rtx/hpc/concurrencyThreads", 4)
        self._settings.set_default("/rtx/hpc/pdeMethod", "ANISOTROPIC_DIFFUSION")
        self._settings.set_default("/rtx/hpc/pdeIterations", 10)
        self._settings.set_default("/rtx/hpc/pdeTimestep", 0.1)
        self._settings.set_default("/rtx/hpc/useWavelet", True)
        self._settings.set_default("/rtx/hpc/enableAiRefinement", True)

    def on_shutdown(self):
        pass
