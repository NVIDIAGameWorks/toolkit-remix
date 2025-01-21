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

import omni.kit.commands
import carb.settings

class SetHpcConfigCommand(omni.kit.commands.Command):
    """Command to set HPC configuration options with undo support"""
    
    def __init__(self, setting_path: str, value, prev_value=None):
        self._settings = carb.settings.get_settings()
        self._setting_path = setting_path
        self._value = value
        self._prev_value = prev_value or self._settings.get(setting_path)

    def do(self):
        """Execute the command"""
        self._settings.set(self._setting_path, self._value)
        return True

    def undo(self):
        """Undo the command"""
        self._settings.set(self._setting_path, self._prev_value)
        return True
