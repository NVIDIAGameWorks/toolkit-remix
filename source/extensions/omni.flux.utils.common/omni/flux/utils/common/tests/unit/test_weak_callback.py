"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("TestWeakCallback",)

import weakref

import omni.kit.test
from omni.flux.utils.common import weak_callback


class TestWeakCallback(omni.kit.test.AsyncTestCase):
    """Exercise weak callback forwarding and ownership contracts."""

    async def test_weak_callback_with_live_owner_forwards_arguments_and_return_value(self):
        """A weak callback preserves the bound method's calling contract."""

        # Arrange
        class Owner:
            """Record callback arguments without external dependencies."""

            def __init__(self):
                """Initialize the observed calls."""
                self.calls = []

            def on_change(self, value, *, scale=1):
                """Record and return the scaled input."""
                self.calls.append(value * scale)
                return value * scale

        owner = Owner()
        callback = weak_callback(owner.on_change)

        # Act
        result = callback(2, scale=3)

        # Assert
        self.assertEqual(result, 6)
        self.assertEqual(owner.calls, [6])

    async def test_weak_callback_after_owner_release_does_not_retain_or_call_owner(self):
        """Retaining a callback does not retain its receiver."""

        # Arrange
        class Owner:
            """Supply a method whose receiver can be released independently."""

            def on_change(self, value):
                """Return the supplied value while the owner exists."""
                return value

        owner = Owner()
        callback = weak_callback(owner.on_change)
        owner_reference = weakref.ref(owner)
        del owner

        # Act
        result = callback(5)

        # Assert
        self.assertIsNone(owner_reference())
        self.assertIsNone(result)
