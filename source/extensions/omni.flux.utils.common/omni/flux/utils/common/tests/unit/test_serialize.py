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

import dataclasses
from decimal import Decimal

import omni.kit.test
from omni.flux.utils.common.serialize import Converter, Serializer

float_converter = Converter(
    key="float",
    claim_func=lambda x: isinstance(x, float),
    serialize_hook=lambda x: x.hex(),
    deserialize_hook=float.fromhex,
)


@dataclasses.dataclass
class Number:
    value: int | float | Decimal


def register_number_converter_hooks(serializer):
    @serializer.register_serialize_hook(Number, key="Number")
    def serialize_number(number):
        return serializer.serialize(number.value)

    @serializer.register_deserialize_hook(Number, key="Number")
    def deserialize_number(n):
        return Number(serializer.deserialize(n))

    @serializer.register_serialize_hook(Decimal, key="Decimal")
    def serialize_decimal(d):
        return str(d.normalize())

    @serializer.register_deserialize_hook(Decimal, key="Decimal")
    def deserialize_decimal(s):
        return Decimal(s)


class TestSerializer(omni.kit.test.AsyncTestCase):
    def test_register_converter(self):
        serializer = Serializer()
        serializer.register_converter(float_converter)
        self.assertTrue(float_converter in serializer._converters)  # noqa PLW0212

    def test_register_decorator_with_type(self):
        serializer = Serializer()

        self.assertTrue(len(serializer._converters) == 0)  # noqa PLW0212

        @serializer.register_serialize_hook(float)
        def serialize_float(f):
            return f.hex()

        self.assertTrue(len(serializer._converters) == 1)  # noqa PLW0212
        self.assertIs(serializer._converters[0].serialize_hook, serialize_float)  # noqa PLW0212

        @serializer.register_deserialize_hook(float)
        def deserialize_float(s):
            return float.fromhex(s)

        # Test we add to existing Converter and don't create a new one.
        self.assertTrue(len(serializer._converters) == 1)  # noqa PLW0212
        self.assertIs(serializer._converters[0].deserialize_hook, deserialize_float)  # noqa PLW0212

    def test_register_decorator_with_claim_func(self):
        serializer = Serializer()

        self.assertTrue(len(serializer._converters) == 0)  # noqa PLW0212

        with self.assertRaises(ValueError):
            # Check using a claim func with no key raises an error.
            @serializer.register_serialize_hook(lambda x: isinstance(x, float))
            def serialize_float_fail(f):
                return f.hex()

        @serializer.register_serialize_hook(lambda x: isinstance(x, float), key="float")
        def serialize_float(f):
            return f.hex()

        self.assertTrue(len(serializer._converters) == 1)  # noqa PLW0212
        self.assertIs(serializer._converters[0].serialize_hook, serialize_float)  # noqa PLW0212

        @serializer.register_deserialize_hook(lambda x: isinstance(x, float), key="float")
        def deserialize_float(s):
            return float.fromhex(s)

        # Test we add to existing Converter and don't create a new one.
        self.assertTrue(len(serializer._converters) == 1)  # noqa PLW0212
        self.assertIs(serializer._converters[0].deserialize_hook, deserialize_float)  # noqa PLW0212

    def test_serialize_and_dumps_no_registered(self):
        serializer = Serializer()

        # The serialize method is a pass-through if no registered converters claim the object
        self.assertEqual(serializer.serialize(42), 42)
        # Json can handle this type natively so dumps should work fine.
        self.assertTrue(serializer.dumps(42) == "42")

        num = Number(Decimal(42))
        self.assertEqual(serializer.serialize(num), num)
        # However, dumps will fail because json doesn't have support for the custom Number object
        with self.assertRaises(TypeError):
            serializer.dumps(num)

    def test_serialize_round_trip(self):
        serializer = Serializer()
        serializer.register_converter(float_converter)
        register_number_converter_hooks(serializer)

        def test_round_trip(native, primitive):
            self.assertEquals(serializer.serialize(native), primitive)
            self.assertEquals(serializer.deserialize(primitive), native)

        test_round_trip(42, 42)
        test_round_trip(42.0, {"_key": "float", "_value": "0x1.5000000000000p+5"})
        test_round_trip(Number(Decimal(42)), {"_key": "Number", "_value": {"_key": "Decimal", "_value": "42"}})

    def test_dumps_loads_round_trip(self):
        serializer = Serializer()
        serializer.register_converter(float_converter)
        register_number_converter_hooks(serializer)

        def test_round_trip(native, jsonstr):
            self.assertEquals(serializer.dumps(native), jsonstr)
            self.assertEquals(serializer.loads(jsonstr), native)

        # int has no registered converter, so it should just pass through to json
        test_round_trip(42, "42")

        # float has a registered converter, so we expect this json
        test_round_trip(42.0, '{"_key": "float", "_value": "0x1.5000000000000p+5"}')

        # Number and Decimal have registered converters, so we expect this json
        test_round_trip(Number(Decimal(42)), '{"_key": "Number", "_value": {"_key": "Decimal", "_value": "42"}}')

    def test_nested(self):
        serializer = Serializer()
        serializer.register_converter(float_converter)

        data = [42, 42.0, {"foo": 42.0, "bar": {"spangle": 42.0}, "epsilon": [41, 43]}]

        expected = [
            42,
            {
                "_key": "float",
                "_value": "0x1.5000000000000p+5",
            },
            {
                "foo": {
                    "_key": "float",
                    "_value": "0x1.5000000000000p+5",
                },
                "bar": {
                    "spangle": {
                        "_key": "float",
                        "_value": "0x1.5000000000000p+5",
                    }
                },
                "epsilon": [41, 43],
            },
        ]

        self.assertEquals(serializer.serialize(data), expected)
