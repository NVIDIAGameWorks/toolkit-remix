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
import time
import numpy as np
from rtx import TextureData, KuoniradHpcPipeline

class TestHpcPerformance(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._settings = carb.settings.get_settings()
        self._pipeline = KuoniradHpcPipeline()
        
        # Create large test textures for stress testing
        self._large_texture = self._create_test_texture(4096, 4096)  # 16M pixels
        self._medium_texture = self._create_test_texture(2048, 2048)  # 4M pixels
        
    def _create_test_texture(self, width: int, height: int) -> TextureData:
        """Create a test texture with random data"""
        texture = TextureData()
        texture.resize(width, height)
        # Fill with random data
        data = np.random.rand(height, width, 4).astype(np.float32)
        texture.pixels()[:] = data.reshape(-1)
        return texture
        
    async def test_cpu_stress_multithreading(self):
        """Test CPU performance with different thread counts"""
        thread_counts = [1, 2, 4, 8, 16]
        results = {}
        
        for threads in thread_counts:
            self._settings.set("/rtx/hpc/concurrencyThreads", threads)
            
            start_time = time.perf_counter()
            # Process medium texture 10 times
            for _ in range(10):
                KuoniradHpcPipeline.runPipeline(self._medium_texture)
            end_time = time.perf_counter()
            
            results[threads] = end_time - start_time
            
        # Verify performance scales with thread count
        # Should see improvement up to physical core count
        for i in range(1, len(thread_counts)-1):
            speedup = results[thread_counts[i-1]] / results[thread_counts[i]]
            self.assertGreater(speedup, 1.2)  # Expect at least 20% speedup
            
    async def test_gpu_stress_large_textures(self):
        """Test GPU performance with large texture processing"""
        self._settings.set("/rtx/hpc/enableAiRefinement", True)
        self._settings.set("/rtx/hpc/useWavelet", True)
        
        # Warm up
        KuoniradHpcPipeline.runPipeline(self._medium_texture)
        
        # Measure large texture processing time
        start_time = time.perf_counter()
        result = KuoniradHpcPipeline.runPipeline(self._large_texture)
        processing_time = time.perf_counter() - start_time
        
        # Verify processing completes within reasonable time
        # 4K texture should process in under 1 second on modern GPU
        self.assertLess(processing_time, 1.0)
        
        # Verify output dimensions match input
        self.assertEqual(result.width(), self._large_texture.width())
        self.assertEqual(result.height(), self._large_texture.height())
        
    async def test_baseline_metrics(self):
        """Establish baseline performance metrics"""
        # Configure standard test settings
        self._settings.set("/rtx/hpc/concurrencyThreads", 4)
        self._settings.set("/rtx/hpc/pdeIterations", 10)
        self._settings.set("/rtx/hpc/useWavelet", True)
        
        # Measure baseline performance
        start_time = time.perf_counter()
        KuoniradHpcPipeline.runPipeline(self._medium_texture)
        baseline_time = time.perf_counter() - start_time
        
        # Store baseline metric
        self._settings.set("/rtx/hpc/baseline/processingTime", baseline_time)
        
        # Verify reasonable performance
        # 2K texture should process in under 250ms
        self.assertLess(baseline_time, 0.25)
