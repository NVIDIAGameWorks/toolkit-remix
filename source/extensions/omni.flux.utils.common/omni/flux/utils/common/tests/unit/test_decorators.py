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

import omni.kit.test
from omni.flux.utils.common.decorators import limit_recursion


@limit_recursion()
def inc_n0(store, c=0):
    c += 1
    store.append(c)
    inc_n0(store, c=c)


@limit_recursion(num_allowed_recursive_calls=2)
def inc_n2(store, c=0):
    c += 1
    store.append(c)
    inc_n2(store, c=c)


@limit_recursion(num_allowed_recursive_calls=2, error=True)
def inc_n2_error(store, c=0):
    c += 1
    store.append(c)
    inc_n2_error(store, c=c)


@limit_recursion()
def inc_return(store, c=0):
    c += 1
    store.append(c)
    return inc_return(store, c=c)


class TestLimitRecursion(omni.kit.test.AsyncTestCase):
    def test_inc_n0(self):
        cache = []
        inc_n0(cache)
        self.assertSequenceEqual(cache, [1])

    def test_inc_n2(self):
        cache = []
        inc_n2(cache)
        self.assertSequenceEqual(cache, [1, 2, 3])

    def test_error(self):
        cache = []
        with self.assertRaises(RecursionError):
            inc_n2_error(cache)
        self.assertSequenceEqual(cache, [1, 2, 3])

    def test_return(self):
        cache = []
        result = inc_return(cache)
        self.assertSequenceEqual(cache, [1])
        self.assertIsNone(result)
