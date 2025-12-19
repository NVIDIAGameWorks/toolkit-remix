# Copyright (c) 2024, NVIDIA CORPORATION. All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto. Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
Utility functions for OmniGraph node type resolution.

This module provides:
1. Standard handlers (standard_compute, standard_initialize) for all nodes
2. Type resolution for flexible-type nodes (resolve_types)
3. Token category validation for semantic type checking

Usage for fixed-type nodes:
    from lightspeed.trex.logic.ogn._impl.type_resolution import standard_compute, standard_initialize

    class MyNode:
        compute = standard_compute
        initialize = standard_initialize

Usage for flexible-type nodes:
    from lightspeed.trex.logic.ogn._impl.type_resolution import (
        standard_compute, standard_initialize, resolve_types
    )

    class MyFlexNode:
        VALID_COMBINATIONS = [...]
        compute = standard_compute
        initialize = standard_initialize

        @staticmethod
        def on_connection_type_resolve(node) -> None:
            resolve_types(node, MyFlexNode.VALID_COMBINATIONS)
"""
from __future__ import annotations

from contextlib import suppress

import carb
import omni.graph.core as og

# Type constants
UNKNOWN = og.Type(og.BaseDataType.UNKNOWN)
TOKEN = og.Type(og.BaseDataType.TOKEN)

# Metadata key for token sub-type categorization
TOKEN_CATEGORY_KEY = "tokenCategory"

# Caches and tracking
_flexible_attrs_cache: dict[str, tuple[list[str], list[str]]] = {}
_most_recent_connection: dict[int, str] = {}
_callback_registered: set[int] = set()


# =============================================================================
# Standard Node Handlers
# =============================================================================


def standard_compute(db) -> bool:
    """Standard compute handler for all nodes.

    Use this as the compute method for nodes that don't need custom compute logic.
    """
    # TODO[REMIX-4814]: This function is currently not being invoked in the Toolkit.
    # Once it does get called, this would be the place to do any value validation.

    # The below function can be used to turn the node yellow, if the input data is invalid somehow.
    # db.log_warning(f"[DEBUG] standard_compute: {db.node.get_prim_path()}")
    return True


def standard_initialize(_context, node) -> None:
    """Standard initialize handler for all nodes.

    Registers connection validation callback when the node is created.
    Use this as the initialize method for all nodes.
    """
    _setup_node_callbacks(node)


# =============================================================================
# Attribute Helper Functions
# =============================================================================


def _is_flexible_attribute(attr) -> bool:
    """Check if an attribute is a flexible type (ANY or UNION)."""
    try:
        extended_type = attr.get_extended_type()
        return extended_type in (og.ExtendedAttributeType.UNION, og.ExtendedAttributeType.ANY)
    except (AttributeError, TypeError):
        return False


def _get_flexible_attributes(node) -> tuple[list[str], list[str]]:
    """Discover flexible (UNION/ANY) attributes from a node. Results are cached."""
    node_type_name = node.get_type_name()

    if node_type_name in _flexible_attrs_cache:
        return _flexible_attrs_cache[node_type_name]

    input_attrs = []
    output_attrs = []

    for attr in node.get_attributes():
        if _is_flexible_attribute(attr):
            port_type = attr.get_port_type()
            name = attr.get_name()
            full_name = name if ":" in name else f"{port_type.name.lower()}s:{name}"

            if port_type == og.AttributePortType.INPUT:
                input_attrs.append(full_name)
            elif port_type == og.AttributePortType.OUTPUT:
                output_attrs.append(full_name)

    _flexible_attrs_cache[node_type_name] = (input_attrs, output_attrs)
    return input_attrs, output_attrs


def _get_type_from_connection(attr) -> og.Type:
    """Get the type from an attribute, falling back to upstream connection if UNKNOWN."""
    resolved = attr.get_resolved_type()
    if resolved != UNKNOWN:
        return resolved

    upstream = attr.get_upstream_connections()
    if upstream:
        return upstream[0].get_resolved_type()

    return UNKNOWN


# =============================================================================
# Token Category Functions
# =============================================================================


def _get_token_category(attr) -> str | None:
    """Get the token category metadata from an attribute, or None if not set."""
    try:
        result = attr.get_metadata(TOKEN_CATEGORY_KEY)
        if result == "" or result is None:
            return None
        return result
    except (AttributeError, TypeError):
        return None


def _get_node_token_category(node) -> str | None:
    """Get the token category from any connected TOKEN input on the node.

    For flexible-type nodes, all TOKEN inputs must have the same category.
    Returns the category from the first connected input that has one.
    """
    for attr in node.get_attributes():
        if attr.get_port_type() != og.AttributePortType.INPUT:
            continue
        if attr.get_resolved_type().base_type != og.BaseDataType.TOKEN:
            continue
        for upstream in attr.get_upstream_connections():
            cat = _get_token_category(upstream)
            if cat is not None:
                return cat
    return None


def _is_token_compatible(attr1, attr2, node_category: str | None = None) -> bool:
    """Check if two TOKEN attributes are compatible based on their category metadata.

    Args:
        attr1: First attribute
        attr2: Second attribute
        node_category: Optional existing token category on the node (for consistency check)
    """
    type1 = attr1.get_resolved_type()
    type2 = attr2.get_resolved_type()

    # If either is not TOKEN, compatibility is determined by type alone
    if type1.base_type != og.BaseDataType.TOKEN or type2.base_type != og.BaseDataType.TOKEN:
        return True

    cat1 = _get_token_category(attr1)
    cat2 = _get_token_category(attr2)
    flex1 = _is_flexible_attribute(attr1)
    flex2 = _is_flexible_attribute(attr2)

    # If both have categories, they must match
    if cat1 is not None and cat2 is not None:
        return cat1 == cat2

    # If either is flexible and doesn't have a category yet, check node consistency
    if (flex1 and cat1 is None) or (flex2 and cat2 is None):
        # If we have an existing node category, the incoming one must match
        incoming_cat = cat1 if cat1 is not None else cat2
        if node_category is not None and incoming_cat is not None:
            return node_category == incoming_cat
        return True

    # Fixed-type attributes without categories are incompatible
    return False


def _propagate_token_category(inputs: dict, outputs: dict) -> None:
    """Propagate token category metadata from connected inputs to outputs."""
    # Find category from any connected input
    input_category = None
    for attr in inputs.values():
        for upstream in attr.get_upstream_connections():
            cat = _get_token_category(upstream)
            if cat is not None:
                input_category = cat
                break
        if input_category:
            break

    # Apply to all TOKEN outputs
    for attr in outputs.values():
        if attr.get_resolved_type().base_type != og.BaseDataType.TOKEN:
            continue
        with suppress(AttributeError, TypeError):
            attr.set_metadata(TOKEN_CATEGORY_KEY, input_category)


# =============================================================================
# Connection Validation
# =============================================================================


def _setup_node_callbacks(node) -> None:
    """Set up connection callbacks for a node (token validation + connection tracking)."""
    node_handle = node.get_handle()
    if node_handle in _callback_registered:
        return

    # Get flexible input names for connection tracking
    input_attr_names, _ = _get_flexible_attributes(node)
    input_attr_names_set = set(input_attr_names)

    def on_connected(from_attr, to_attr):
        try:
            # Track most recent connection for flexible inputs (for conflict resolution)
            to_name = to_attr.get_name()
            full_name = f"inputs:{to_name}" if not to_name.startswith("inputs:") else to_name
            if full_name in input_attr_names_set or to_name in input_attr_names_set:
                _most_recent_connection[node_handle] = full_name

            # Get existing node token category for consistency check
            existing_category = _get_node_token_category(node)

            # Check token compatibility (including node-wide category consistency)
            is_compatible = _is_token_compatible(to_attr, from_attr, existing_category)
            if not is_compatible and to_attr.is_connected(from_attr):
                _log_token_rejection(from_attr, to_attr, existing_category)
                from_attr.disconnect(to_attr, modify_usd=True)
        except (AttributeError, TypeError, RuntimeError) as e:
            carb.log_error(f"on_connected exception: {e}")

    try:
        node.register_on_connected_callback(on_connected)
        _callback_registered.add(node_handle)
    except (AttributeError, TypeError) as e:
        carb.log_error(f"Failed to register on_connected callback: {e}")


def _log_token_rejection(from_attr, to_attr, node_category: str | None) -> None:
    """Log a warning when a token connection is rejected."""
    from_cat = _get_token_category(from_attr) or "Flexible"
    to_cat = _get_token_category(to_attr) or "Unknown"
    node_cat_msg = f" (node has '{node_category}')" if node_category else ""
    carb.log_warn(
        f"[OmniGraph] Rejected connection: '{from_cat}' -> '{to_cat}'{node_cat_msg} "
        f"({from_attr.get_path()} -> {to_attr.get_path()})"
    )


def _disconnect_incompatible(attr, valid_types: set, node_category: str | None, upstream: bool) -> None:
    """Disconnect connections whose type is not in valid_types or have incompatible token categories.

    If valid_types is empty, ALL connections are considered type-incompatible and will be disconnected.
    """
    connections = attr.get_upstream_connections() if upstream else attr.get_downstream_connections()

    for other_attr in list(connections):
        other_type = other_attr.get_resolved_type()
        # If valid_types is empty, any non-UNKNOWN type is incompatible
        type_incompatible = other_type != UNKNOWN and (not valid_types or other_type not in valid_types)
        token_incompatible = not _is_token_compatible(attr, other_attr, node_category)

        if not (type_incompatible or token_incompatible):
            continue

        try:
            if upstream and attr.is_connected(other_attr):
                if token_incompatible and not type_incompatible:
                    _log_token_rejection(other_attr, attr, node_category)
                other_attr.disconnect(attr, modify_usd=True)
            elif not upstream and other_attr.is_connected(attr):
                if token_incompatible and not type_incompatible:
                    _log_token_rejection(attr, other_attr, node_category)
                attr.disconnect(other_attr, modify_usd=True)
        except (AttributeError, TypeError, RuntimeError) as e:
            carb.log_error(f"_disconnect_incompatible exception: {e}")


# =============================================================================
# Type Resolution
# =============================================================================


def _get_valid_types(attr_name: str, known_types: dict[str, og.Type], valid_combinations: list[dict]) -> set:
    """Get all valid types for an attribute given known types of other attributes."""
    valid_types = set()
    for combo in valid_combinations:
        if attr_name not in combo:
            continue
        if all(known_type in (UNKNOWN, combo.get(name, UNKNOWN)) for name, known_type in known_types.items()):
            valid_types.add(combo[attr_name])
    return valid_types


def _find_unique_type(attr_name: str, known_types: dict[str, og.Type], valid_combinations: list[dict]) -> og.Type:
    """Find the type for an attribute if uniquely determined."""
    valid_types = _get_valid_types(attr_name, known_types, valid_combinations)
    if len(valid_types) == 1:
        return next(iter(valid_types))
    return UNKNOWN


def resolve_types(node, valid_combinations: list[dict]) -> None:
    """Resolve flexible attribute types based on valid combinations.

    Call this from on_connection_type_resolve for all nodes.
    For fixed-type nodes, pass an empty list [] - callbacks handle token validation.

    Args:
        node: The OmniGraph node
        valid_combinations: List of dicts mapping attribute names to types (can be empty)
    """
    # Ensure callbacks are registered
    _setup_node_callbacks(node)

    # For fixed-type nodes (empty valid_combinations), callbacks handle everything
    if not valid_combinations:
        return

    input_attr_names, output_attr_names = _get_flexible_attributes(node)
    node_handle = node.get_handle()

    inputs = {name: node.get_attribute(name) for name in input_attr_names}
    outputs = {name: node.get_attribute(name) for name in output_attr_names}

    input_connected = {name: attr.get_upstream_connection_count() > 0 for name, attr in inputs.items()}
    input_types = {name: _get_type_from_connection(attr) for name, attr in inputs.items()}

    # No inputs connected - reset all to UNKNOWN
    if not any(input_connected.values()):
        for attr in list(inputs.values()) + list(outputs.values()):
            attr.set_resolved_type(UNKNOWN)
        return

    # Get existing node token category for consistency checks
    node_category = _get_node_token_category(node)

    # Find most recently connected input (has lowest priority in conflicts)
    most_recent_attr = _most_recent_connection.get(node_handle)

    # Build list of connected input names, with most recent last
    connected_names = [name for name in input_attr_names if input_connected[name] and input_types[name] != UNKNOWN]
    if most_recent_attr and most_recent_attr in connected_names:
        connected_names.remove(most_recent_attr)
        connected_names.append(most_recent_attr)

    # Process inputs - earlier has priority, disconnect conflicts
    known_types: dict[str, og.Type] = {}
    for name in connected_names:
        valid_types = _get_valid_types(name, known_types, valid_combinations)
        if input_types[name] in valid_types:
            known_types[name] = input_types[name]
        else:
            _disconnect_incompatible(inputs[name], valid_types, node_category, upstream=True)

    # Refresh after disconnections
    input_connected = {name: attr.get_upstream_connection_count() > 0 for name, attr in inputs.items()}
    input_types = {name: attr.get_resolved_type() for name, attr in inputs.items()}
    known_types = {
        name: input_types[name] for name in input_attr_names if input_connected[name] and input_types[name] != UNKNOWN
    }

    # Resolve unconnected inputs FIRST (OmniGraph requires consistent state)
    for name, attr in inputs.items():
        if not input_connected[name]:
            attr.set_resolved_type(_find_unique_type(name, known_types, valid_combinations))

    # Resolve outputs
    for name, attr in outputs.items():
        attr.set_resolved_type(_find_unique_type(name, known_types, valid_combinations))

    # Propagate token category from inputs to outputs
    _propagate_token_category(inputs, outputs)

    # Disconnect incompatible downstream connections
    for name, attr in outputs.items():
        _disconnect_incompatible(
            attr, _get_valid_types(name, known_types, valid_combinations), node_category, upstream=False
        )
