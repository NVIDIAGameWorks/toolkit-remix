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

import omni.kit.test
import carb.settings

class TestHpcConfig(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._settings = carb.settings.get_settings()
        # Store original values
        self._original_values = {
            "/rtx/hpc/enablePipeline": self._settings.get("/rtx/hpc/enablePipeline"),
            "/rtx/hpc/concurrencyThreads": self._settings.get("/rtx/hpc/concurrencyThreads"),
            "/rtx/hpc/pdeMethod": self._settings.get("/rtx/hpc/pdeMethod"),
            "/rtx/hpc/pdeIterations": self._settings.get("/rtx/hpc/pdeIterations"),
            "/rtx/hpc/pdeTimestep": self._settings.get("/rtx/hpc/pdeTimestep"),
            "/rtx/hpc/useWavelet": self._settings.get("/rtx/hpc/useWavelet"),
            "/rtx/hpc/enableAiRefinement": self._settings.get("/rtx/hpc/enableAiRefinement")
        }

    async def tearDown(self):
        # Restore original values
        for key, value in self._original_values.items():
            self._settings.set(key, value)

    async def test_default_values(self):
        """Test that default values are set correctly"""
        self.assertTrue(self._settings.get("/rtx/hpc/enablePipeline"))
        self.assertEqual(self._settings.get("/rtx/hpc/concurrencyThreads"), 4)
        self.assertEqual(self._settings.get("/rtx/hpc/pdeMethod"), "ANISOTROPIC_DIFFUSION")
        self.assertEqual(self._settings.get("/rtx/hpc/pdeIterations"), 10)
        self.assertEqual(self._settings.get("/rtx/hpc/pdeTimestep"), 0.1)
        self.assertTrue(self._settings.get("/rtx/hpc/useWavelet"))
        self.assertTrue(self._settings.get("/rtx/hpc/enableAiRefinement"))

    async def test_set_config_command(self):
        """Test the SetHpcConfigCommand for setting and undoing changes"""
        from ..commands import SetHpcConfigCommand
        
        # Test setting a new value
        cmd = SetHpcConfigCommand("/rtx/hpc/concurrencyThreads", 8)
        self.assertTrue(await omni.kit.test.utils.run_async_command(cmd))
        self.assertEqual(self._settings.get("/rtx/hpc/concurrencyThreads"), 8)
        
        # Test undoing the change
        self.assertTrue(await omni.kit.test.utils.undo_async_command(cmd))
        self.assertEqual(self._settings.get("/rtx/hpc/concurrencyThreads"), 4)

    async def test_pde_method_validation(self):
        """Test that only valid PDE methods are accepted"""
        from ..commands import SetHpcConfigCommand
        
        # Test valid method
        cmd = SetHpcConfigCommand("/rtx/hpc/pdeMethod", "POISSON_BLENDING")
        self.assertTrue(await omni.kit.test.utils.run_async_command(cmd))
        self.assertEqual(self._settings.get("/rtx/hpc/pdeMethod"), "POISSON_BLENDING")
        
        # Test invalid method (should keep previous value)
        cmd = SetHpcConfigCommand("/rtx/hpc/pdeMethod", "INVALID_METHOD")
        with self.assertRaises(ValueError):
            await omni.kit.test.utils.run_async_command(cmd)
        self.assertEqual(self._settings.get("/rtx/hpc/pdeMethod"), "POISSON_BLENDING")
