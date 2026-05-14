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

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.conditional_visibility_orchestrator.expression_evaluator import (
    evaluate_expression,
    extract_identifiers,
    normalize_expression,
)


class TestExpressionEvaluator(omni.kit.test.AsyncTestCase):
    """Unit tests for the constrained MDL-style enable-if expression evaluator."""

    async def test_evaluate_expression_eq_returns_true_for_matching_constants(self):
        # Arrange
        expression = "True == True"

        # Act
        result = evaluate_expression(expression, {})

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_eq_returns_false_for_mismatched_values(self):
        # Arrange
        values = {"driver": False}

        # Act
        result = evaluate_expression("driver == True", values)

        # Assert
        self.assertFalse(result)

    async def test_evaluate_expression_neq_returns_true_for_distinct_values(self):
        # Arrange
        values = {"driver": False}

        # Act
        result = evaluate_expression("driver != True", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_neq_returns_false_for_equal_values(self):
        # Arrange
        values = {"driver": True}

        # Act
        result = evaluate_expression("driver != True", values)

        # Assert
        self.assertFalse(result)

    async def test_evaluate_expression_and_returns_true_when_all_operands_true(self):
        # Arrange
        values = {"a": True, "b": True}

        # Act
        result = evaluate_expression("a && b", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_and_returns_false_when_any_operand_false(self):
        # Arrange
        values = {"a": True, "b": False}

        # Act
        result = evaluate_expression("a && b", values)

        # Assert
        self.assertFalse(result)

    async def test_evaluate_expression_or_returns_true_when_any_operand_true(self):
        # Arrange
        values = {"a": False, "b": True}

        # Act
        result = evaluate_expression("a || b", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_or_returns_false_when_all_operands_false(self):
        # Arrange
        values = {"a": False, "b": False}

        # Act
        result = evaluate_expression("a || b", values)

        # Assert
        self.assertFalse(result)

    async def test_evaluate_expression_unary_not_inverts_truthy_value(self):
        # Arrange
        values = {"a": True}

        # Act
        result = evaluate_expression("!a", values)

        # Assert
        self.assertFalse(result)

    async def test_evaluate_expression_unary_not_preserves_falsy_value(self):
        # Arrange
        values = {"a": False}

        # Act
        result = evaluate_expression("!a", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_treats_uppercase_true_as_true_constant(self):
        # Arrange
        expression = "TRUE == True"

        # Act
        result = evaluate_expression(expression, {})

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_treats_lowercase_false_as_false_constant(self):
        # Arrange
        values = {"driver": False}

        # Act
        result = evaluate_expression("driver == false", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_treats_one_as_boolean_friendly(self):
        # Arrange
        values = {"flag": 1}

        # Act
        result = evaluate_expression("flag == True", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_treats_zero_as_boolean_friendly(self):
        # Arrange
        values = {"flag": 0}

        # Act
        result = evaluate_expression("flag == False", values)

        # Assert
        self.assertTrue(result)

    async def test_evaluate_expression_raises_for_missing_identifier_in_compare(self):
        # Arrange
        values: dict = {}

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression("driver == True", values)

    async def test_evaluate_expression_raises_for_bare_identifier_with_none_value(self):
        # Arrange
        values = {"flag": None}

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression("flag", values)

    async def test_evaluate_expression_raises_for_unsupported_addition_syntax(self):
        # Arrange
        values = {"a": True, "b": False}

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression("a + b", values)

    async def test_evaluate_expression_raises_for_chained_comparisons(self):
        # Arrange
        values = {"a": True, "b": True, "c": True}

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression("a == b == c", values)

    async def test_evaluate_expression_raises_for_unsupported_less_than_operator(self):
        # Arrange
        values = {"a": True, "b": False}

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression("a < b", values)

    async def test_evaluate_expression_raises_for_non_boolean_friendly_value(self):
        # Arrange
        values = {"a": "yes"}

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression("a == True", values)

    async def test_evaluate_expression_raises_for_empty_expression(self):
        # Arrange
        expression = ""

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression(expression, {})

    async def test_evaluate_expression_raises_for_unmatched_parenthesis(self):
        # Arrange
        expression = "not(parseable"

        # Act / Assert
        with self.assertRaises(ValueError):
            evaluate_expression(expression, {"parseable": True})

    async def test_extract_identifiers_returns_unique_names_in_first_seen_order(self):
        # Arrange
        expression = "a && b || a"

        # Act
        identifiers = extract_identifiers(expression)

        # Assert
        self.assertEqual(identifiers, ("a", "b"))

    async def test_extract_identifiers_excludes_boolean_literals(self):
        # Arrange
        expression = "driver == True"

        # Act
        identifiers = extract_identifiers(expression)

        # Assert
        self.assertEqual(identifiers, ("driver",))

    async def test_extract_identifiers_returns_empty_for_constants_only(self):
        # Arrange
        expression = "True == False"

        # Act
        identifiers = extract_identifiers(expression)

        # Assert
        self.assertEqual(identifiers, ())

    async def test_extract_identifiers_raises_for_invalid_syntax(self):
        # Arrange
        expression = "a +"

        # Act / Assert
        with self.assertRaises(ValueError):
            extract_identifiers(expression)

    async def test_normalize_expression_replaces_mdl_keywords_and_operators(self):
        # Arrange
        expression = "a && b || !c"

        # Act
        normalized = normalize_expression(expression)

        # Assert
        self.assertNotIn("&&", normalized)
        self.assertNotIn("||", normalized)
        self.assertNotIn("!", normalized)
        self.assertIn(" and ", normalized)
        self.assertIn(" or ", normalized)
        self.assertIn(" not ", normalized)

    async def test_normalize_expression_preserves_not_equal_operator(self):
        # Arrange
        expression = "a != b"

        # Act
        normalized = normalize_expression(expression)

        # Assert
        self.assertIn("!=", normalized)
        self.assertNotIn(" not ", normalized)

    async def test_normalize_expression_capitalizes_lowercase_true_and_false(self):
        # Arrange
        expression = "flag == true && other == false"

        # Act
        normalized = normalize_expression(expression)

        # Assert
        self.assertIn("True", normalized)
        self.assertIn("False", normalized)
        self.assertNotIn(" true ", normalized)
        self.assertNotIn(" false ", normalized)
