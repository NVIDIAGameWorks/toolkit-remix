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

__all__ = [
    "RESOLVER_PLUGINS",
    "TEXTURE_RESOLVER_PLUGINS",
    "AllStageTexturesResolver",
    "ConstantResolver",
    "LayerIdentifierResolver",
    "ResolverConfigurationError",
    "ResolverFactory",
    "ResolverParameter",
    "ResolverRule",
    "ResolverValueError",
    "SelectedPrimPathResolver",
    "SelectedTextureResolver",
    "StageExpandingResolver",
    "TextureResolverBase",
    "ValueResolver",
    "create_default_resolver",
    "create_resolver",
    "get_resolver_factory",
    "get_resolver_rule",
    "normalize_native_value",
]

from .base import (
    ResolverConfigurationError,
    ResolverFactory,
    ResolverParameter,
    ResolverRule,
    ResolverValueError,
    StageExpandingResolver,
    ValueResolver,
    normalize_native_value,
)
from .builtin import ConstantResolver, LayerIdentifierResolver, SelectedPrimPathResolver
from .textures import (
    TEXTURE_RESOLVER_PLUGINS,
    AllStageTexturesResolver,
    SelectedTextureResolver,
    TextureResolverBase,
)
from ..enums import RemixType

# Semantic texture getters lead the catalog (first entry stays the default), then
# native getters, then the Constant fallback.
RESOLVER_PLUGINS = [
    *TEXTURE_RESOLVER_PLUGINS,
    SelectedPrimPathResolver,
    LayerIdentifierResolver,
    ConstantResolver,
]

_resolver_factory = ResolverFactory()


def get_resolver_factory() -> ResolverFactory:
    """Return the process-owned resolver plugin factory.

    Returns:
        Resolver factory populated by the ComfyUI core extension lifecycle.
    """
    return _resolver_factory


def get_resolver_rule(remix_type: RemixType | None, native_type: type) -> ResolverRule:
    """Return the registered semantic/native waterfall and Constant fallback.

    Args:
        remix_type: Optional product semantic type for the workflow input.
        native_type: Native Python value type declared by the workflow input.

    Returns:
        Registered resolver options and their preferred default.
    """
    return get_resolver_factory().get_rule(remix_type, native_type)


def create_default_resolver(
    remix_type: RemixType | None,
    native_type: type,
    default_value: object,
    context_name: str | None = None,
) -> ValueResolver:
    """Create the configured default resolver for a workflow input.

    Args:
        remix_type: Optional product semantic type for the workflow input.
        native_type: Native Python value type declared by the workflow input.
        default_value: Authored workflow value validated against the declared native type.
        context_name: USD context semantic resolvers should inspect.

    Returns:
        Default resolver selected by the combined resolver rule.
    """
    resolver_type = get_resolver_rule(remix_type, native_type).default
    return create_resolver(resolver_type, native_type, default_value, context_name)


def create_resolver(
    resolver_type: type[ValueResolver],
    native_type: type,
    default_value: object,
    context_name: str | None = None,
) -> ValueResolver:
    """Create one selected resolver with its correctly typed USD default.

    Args:
        resolver_type: Exact resolver class selected from the shared catalog.
        native_type: Native Python type declared by the workflow input.
        default_value: Authored workflow value validated for Constants and passed to other resolvers.
        context_name: USD context semantic resolvers should inspect.

    Returns:
        Resolver initialized for the workflow input.
    """
    if resolver_type is ConstantResolver:
        normalize_native_value(native_type, default_value)
        return ConstantResolver(value_type=native_type)
    return resolver_type.create(default_value, context_name)
