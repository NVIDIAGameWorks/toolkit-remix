"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import datetime
from unittest import mock

import omni.flux.job_queue.core.utils
import omni.kit.test


def my_func():
    pass


class MyClass:
    @classmethod
    def alt_constructor(cls):
        return cls()

    def instance_method(self):
        return "instance"


class TestUtils(omni.kit.test.AsyncTestCase):
    async def test_utils_get_dotted_import_path(self):
        tests = [
            (str, "str"),
            (ValueError, "ValueError"),
            (datetime.datetime, "datetime.datetime"),
            (my_func, "omni.flux.job_queue.core.tests.unit.test_utils.my_func"),
            (MyClass, "omni.flux.job_queue.core.tests.unit.test_utils.MyClass"),
            (
                MyClass.alt_constructor,
                "omni.flux.job_queue.core.tests.unit.test_utils.MyClass.alt_constructor",
            ),
        ]
        for input_obj, expected in tests:
            with self.subTest(name=str(expected)):
                dotted_path = omni.flux.job_queue.core.utils.get_dotted_import_path(input_obj)
                self.assertEqual(dotted_path, expected)

    async def test_utils_import_type_from_path(self):
        tests = [
            (str, "str"),
            (ValueError, "ValueError"),
            (datetime.datetime, "datetime.datetime"),
            (my_func, "omni.flux.job_queue.core.tests.unit.test_utils.my_func"),
            (MyClass, "omni.flux.job_queue.core.tests.unit.test_utils.MyClass"),
            (
                MyClass.alt_constructor,
                "omni.flux.job_queue.core.tests.unit.test_utils.MyClass.alt_constructor",
            ),
        ]
        for expected_obj, dotted_path in tests:
            with self.subTest(name=str(dotted_path)):
                imported_obj = omni.flux.job_queue.core.utils.import_type_from_path(dotted_path)
                self.assertEqual(imported_obj, expected_obj)

    async def test_utils_time_ms(self):
        with mock.patch("time.time_ns", side_effect=lambda: 123456000000):
            self.assertEqual(omni.flux.job_queue.core.utils.time_ms(), 123456)

    async def test_utils_uuid7_uniqueness(self):
        uuids = {omni.flux.job_queue.core.utils.uuid7() for _ in range(100)}
        self.assertEqual(len(uuids), 100)

    async def test_weak_ref_regular_function(self):
        """Test WeakRef with a regular function."""
        weak_func = omni.flux.job_queue.core.utils.WeakRef(my_func)
        self.assertTrue(weak_func.is_alive())
        self.assertEqual(weak_func.get(), my_func)

    async def test_weak_ref_class_method(self):
        """Test WeakRef with a class method."""
        weak_method = omni.flux.job_queue.core.utils.WeakRef(MyClass.alt_constructor)
        self.assertTrue(weak_method.is_alive())
        self.assertEqual(weak_method.get(), MyClass.alt_constructor)

    async def test_weak_ref_bound_method(self):
        """Test WeakRef with a bound method."""
        obj = MyClass()
        weak_method = omni.flux.job_queue.core.utils.WeakRef(obj.instance_method)
        self.assertTrue(weak_method.is_alive())
        self.assertIsNotNone(weak_method.get())

        # Delete the object and verify the weak reference is dead
        del obj
        self.assertFalse(weak_method.is_alive())
        self.assertIsNone(weak_method.get())

    async def test_weak_ref_custom_object(self):
        """Test WeakRef with a custom object."""
        obj = MyClass()
        weak_obj = omni.flux.job_queue.core.utils.WeakRef(obj)
        self.assertTrue(weak_obj.is_alive())
        self.assertIs(weak_obj.get(), obj)

        # Delete the object and verify the weak reference is dead
        del obj
        self.assertFalse(weak_obj.is_alive())
        self.assertIsNone(weak_obj.get())

    async def test_weak_ref_builtin_types(self):
        """Test WeakRef with built-in types that don't support weak references."""
        # These should fall back to direct references
        weak_int = omni.flux.job_queue.core.utils.WeakRef(42)
        weak_str = omni.flux.job_queue.core.utils.WeakRef("test")
        weak_list = omni.flux.job_queue.core.utils.WeakRef([1, 2, 3])

        self.assertTrue(weak_int.is_alive())
        self.assertEqual(weak_int.get(), 42)

        self.assertTrue(weak_str.is_alive())
        self.assertEqual(weak_str.get(), "test")

        self.assertTrue(weak_list.is_alive())
        self.assertEqual(weak_list.get(), [1, 2, 3])

    async def test_weak_ref_lambda(self):
        """Test WeakRef with a lambda function."""

        def lambda_func(x):
            return x * 2

        weak_lambda = omni.flux.job_queue.core.utils.WeakRef(lambda_func)
        self.assertTrue(weak_lambda.is_alive())
        func = weak_lambda.get()
        self.assertIsNotNone(func)
        self.assertEqual(func(5), 10)
