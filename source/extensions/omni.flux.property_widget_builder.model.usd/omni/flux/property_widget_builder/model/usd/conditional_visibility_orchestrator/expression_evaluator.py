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

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from typing import Any

__all__ = ["evaluate_expression", "extract_identifiers", "normalize_expression"]

_TRUE_PATTERN = re.compile(r"\btrue\b", flags=re.IGNORECASE)
_FALSE_PATTERN = re.compile(r"\bfalse\b", flags=re.IGNORECASE)
_NOT_PATTERN = re.compile(r"!(?!=)")


def extract_identifiers(expression: str) -> tuple[str, ...]:
    """Return identifier names referenced by a supported enable-if expression.

    Args:
        expression: MDL-style boolean expression to inspect.

    Returns:
        Unique identifier names in first-seen order.

    Raises:
        ValueError: If the expression cannot be parsed or uses unsupported syntax.
    """
    tree = _parse_expression(expression)
    identifiers: list[str] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in seen:
            identifiers.append(node.id)
            seen.add(node.id)

    return tuple(identifiers)


def evaluate_expression(expression: str, values: Mapping[str, Any]) -> bool:
    """Evaluate a constrained MDL-style boolean expression.

    Args:
        expression: MDL-style boolean expression to evaluate.
        values: Mapping of identifier names to boolean-compatible values.

    Returns:
        Whether the expression evaluates to true.

    Raises:
        ValueError: If parsing, validation, or value coercion fails.
    """
    tree = _parse_expression(expression)
    return _evaluate_node(tree.body, values)


def normalize_expression(expression: str) -> str:
    """Normalize MDL-style boolean syntax into a Python AST-compatible string.

    Args:
        expression: MDL-style boolean expression using operators such as ``&&``, ``||``, or ``!``.

    Returns:
        Expression text normalized for Python ``ast.parse(..., mode="eval")``.
    """
    normalized = expression.strip()
    normalized = normalized.replace("&&", " and ")
    normalized = normalized.replace("||", " or ")
    normalized = _NOT_PATTERN.sub(" not ", normalized)
    normalized = _TRUE_PATTERN.sub("True", normalized)
    normalized = _FALSE_PATTERN.sub("False", normalized)
    return normalized.strip()


def _parse_expression(expression: str) -> ast.Expression:
    """Parse and validate a constrained enable-if expression.

    Args:
        expression: MDL-style boolean expression to parse.

    Returns:
        Parsed Python AST expression.

    Raises:
        ValueError: If the expression is syntactically invalid or unsupported.
    """
    try:
        tree = ast.parse(normalize_expression(expression), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid enable-if expression: {expression!r}") from exc

    _validate_node(tree)
    return tree


def _validate_node(node: ast.AST) -> None:
    """Validate that an AST only contains the supported expression subset.

    Args:
        node: AST node to validate recursively.

    Raises:
        ValueError: If any child node type is unsupported.
    """
    allowed_nodes = (
        ast.And,
        ast.BoolOp,
        ast.Compare,
        ast.Constant,
        ast.Eq,
        ast.Expression,
        ast.Load,
        ast.Name,
        ast.Not,
        ast.NotEq,
        ast.Or,
        ast.UnaryOp,
    )
    for child in ast.walk(node):
        if not isinstance(child, allowed_nodes):
            raise ValueError(f"Unsupported enable-if expression node: {type(child).__name__}")


def _evaluate_node(node: ast.AST, values: Mapping[str, Any]) -> bool:
    """Evaluate a supported AST node as a boolean value.

    Args:
        node: AST node from a validated enable-if expression.
        values: Mapping of identifier names to boolean-compatible values.

    Returns:
        Boolean result for the node.

    Raises:
        ValueError: If the node or operator is unsupported.
    """
    if isinstance(node, ast.BoolOp):
        evaluated_values = [_evaluate_node(value, values) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(evaluated_values)
        if isinstance(node.op, ast.Or):
            return any(evaluated_values)
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _evaluate_node(node.operand, values)

    if isinstance(node, ast.Compare):
        return _evaluate_compare(node, values)

    if isinstance(node, ast.Name):
        return _coerce_bool(values.get(node.id, None), node.id)

    if isinstance(node, ast.Constant):
        return _coerce_bool(node.value, repr(node.value))

    raise ValueError(f"Unsupported enable-if expression node: {type(node).__name__}")


def _evaluate_compare(node: ast.Compare, values: Mapping[str, Any]) -> bool:
    """Evaluate a supported bool-coerced equality or inequality comparison.

    Args:
        node: Comparison node from a validated enable-if expression.
        values: Mapping of identifier names to boolean-compatible values.

    Returns:
        Boolean result from comparing the coerced operands.

    Raises:
        ValueError: If the comparison shape or operator is unsupported.
    """
    if len(node.ops) != 1 or len(node.comparators) != 1:
        raise ValueError("Chained comparisons are not supported in enable-if expressions")

    left = _evaluate_operand(node.left, values)
    right = _evaluate_operand(node.comparators[0], values)

    if isinstance(node.ops[0], ast.Eq):
        return left == right
    if isinstance(node.ops[0], ast.NotEq):
        return left != right
    raise ValueError(f"Unsupported comparison operator: {type(node.ops[0]).__name__}")


def _evaluate_operand(node: ast.AST, values: Mapping[str, Any]) -> bool:
    """Evaluate a comparison operand into a boolean value.

    Args:
        node: Operand node from a validated comparison.
        values: Mapping of identifier names to boolean-compatible values.

    Returns:
        Boolean value produced by coercing the operand.

    Raises:
        ValueError: If the operand is unsupported or references a missing identifier.
    """
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError(f"Missing enable-if value for identifier: {node.id}")
        return _coerce_bool(values[node.id], node.id)

    if isinstance(node, ast.Constant):
        return _coerce_bool(node.value, repr(node.value))

    raise ValueError(f"Unsupported comparison operand: {type(node).__name__}")


def _coerce_bool(value: Any, label: str) -> bool:
    """Coerce an enable-if value to ``bool`` when it is safe to do so.

    Args:
        value: Runtime value to coerce.
        label: Identifier or literal label used in error messages.

    Returns:
        Boolean representation of the value.

    Raises:
        ValueError: If the value is not boolean-compatible.
    """
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"Enable-if value for {label} is not boolean-friendly: {value!r}")
