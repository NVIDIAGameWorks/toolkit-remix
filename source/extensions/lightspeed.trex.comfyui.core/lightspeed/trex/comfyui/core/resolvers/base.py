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
    "ResolverConfigurationError",
    "ResolverFactory",
    "ResolverParameter",
    "ResolverRule",
    "ResolverValueError",
    "StageExpandingResolver",
    "ValueResolver",
    "normalize_native_value",
]

import abc
import dataclasses
import pathlib
from collections.abc import Callable, Iterator
from typing import Any, ClassVar, Generic, TypeVar

from omni.flux.factory.base import FactoryBase, PluginBase
from pxr import Sdf, Usd

from ..enums import RemixType
from ..keys import type_key
from ..maps import NATIVE_TYPE_TO_USD_VALUE_TYPE

ResolvedValueT = TypeVar("ResolvedValueT")
ParameterValueT = TypeVar("ParameterValueT")


class ResolverValueError(ValueError):
    """Report a workflow input value that could not be resolved for a user-facing reason."""


class ResolverConfigurationError(ValueError):
    """Report invalid resolver configuration that must block queue submission."""


@dataclasses.dataclass(frozen=True)
class ResolverParameter(Generic[ParameterValueT]):
    """Strongly typed binding for an editable resolver parameter."""

    name: str
    value_type: type
    get_value: Callable[[], ParameterValueT]
    set_value: Callable[[ParameterValueT], None]
    choices: tuple[ParameterValueT, ...] | None = None
    label: str | None = None
    tooltip: str = ""


@dataclasses.dataclass
class ValueResolver(PluginBase, Generic[ResolvedValueT], abc.ABC):
    """Base class for values resolved from a selected USD prim."""

    name: ClassVar[str]
    label: ClassVar[str]
    remix_types: ClassVar[tuple[RemixType, ...]] = ()
    native_types: ClassVar[tuple[type, ...]] = ()
    is_fallback: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Derive the stable factory and persistence key from the class name.

        Keeps every getter's ``name`` in lockstep with its type so no resolver
        carries a hand-written string key that can silently drift from the class
        it identifies.

        Args:
            **kwargs: Subclass keyword arguments forwarded to the base implementation.
        """
        super().__init_subclass__(**kwargs)
        cls.name = type_key(cls)

    @property
    def parameters(self) -> tuple[ResolverParameter[Any], ...]:
        """Return the resolver's editable parameter bindings.

        Returns:
            Editable parameter bindings, or an empty tuple when the resolver has no settings.
        """
        return ()

    @classmethod
    def create(cls, default_value: object, context_name: str | None = None) -> "ValueResolver":
        """Create this resolver for a workflow input and USD context.

        Args:
            default_value: Authored workflow value used to initialize the resolver.
            context_name: USD context the resolver should inspect when resolving values.

        Returns:
            Resolver initialized for the workflow input.
        """
        return cls()

    @abc.abstractmethod
    def __call__(self, prim: Usd.Prim) -> ResolvedValueT:
        """Resolve a value from a USD prim.

        Args:
            prim: Selected USD prim that supplies semantic input data.

        Returns:
            Value resolved for the workflow input.
        """


class StageExpandingResolver(abc.ABC):
    """Capability mixin for getters that expand a submission across matching stage prims.

    Resolving a single selected prim behaves like the getter's non-expanding sibling. Selecting a
    stage-expanding getter instead turns the submission into one job per matching stage candidate
    (for example every stage material) rather than only the current selection. A new whole-stage
    getter -- all meshes, all lights, and so on -- only needs to mix this in and provide its seed
    prim iterator. It can also filter each value after the normal resolver runs once; the core
    discovers the capability by type and needs no change per getter.
    """

    @abc.abstractmethod
    def iter_stage_prim_paths(self, stage: Usd.Stage) -> Iterator[str]:
        """Iterate the seed prim paths this getter expands the submission across.

        Args:
            stage: Live stage traversed to seed one candidate per matching prim.

        Yields:
            Prim paths whose bound materials become submission candidates.
        """

    def accepts_resolved_value(self, value: object) -> bool:
        """Return whether a resolved candidate value should produce a job.

        Args:
            value: Value resolved once for the expanded candidate.

        Returns:
            Whether the candidate should produce one expanded job. The default accepts every value.
        """
        return True


@dataclasses.dataclass(frozen=True)
class ResolverRule:
    """Declares compatible resolver classes and their preferred default."""

    options: tuple[type[ValueResolver], ...]
    default: type[ValueResolver]

    def __post_init__(self) -> None:
        """Validate that the declared default is one of the offered classes.

        Raises:
            ValueError: If the default resolver is absent from the available options.
        """
        if self.default not in self.options:
            raise ValueError("Resolver rule default must be included in its options")


class ResolverFactory(FactoryBase[ValueResolver]):
    """Build ordered resolver rules from explicitly registered getter plugins."""

    def get_rule(self, remix_type: RemixType | None, native_type: type) -> ResolverRule:
        """Return semantic getters, native getters, and one Constant fallback.

        Args:
            remix_type: Optional product semantic type for the workflow input.
            native_type: Exact native Python type declared by the workflow input.

        Returns:
            Ordered compatible resolver classes and the preferred default.

        Raises:
            RuntimeError: If the Constant fallback plugin is not registered.
        """
        plugins = tuple(self.get_all_plugins().values())
        fallback_plugins = tuple(plugin for plugin in plugins if plugin.is_fallback)
        if len(fallback_plugins) != 1:
            raise RuntimeError("Resolver catalog requires exactly one Constant fallback plugin")
        fallback = fallback_plugins[0]
        semantic = tuple(plugin for plugin in plugins if remix_type is not None and remix_type in plugin.remix_types)
        native = tuple(plugin for plugin in plugins if native_type in plugin.native_types)
        options = tuple(dict.fromkeys((*semantic, *native, fallback)))
        return ResolverRule(options=options, default=semantic[0] if semantic else fallback)


def normalize_native_value(native_type: type, value: object) -> object:
    """Normalize a workflow value for its exact declared native type.

    Args:
        native_type: Native Python type declared by the workflow input.
        value: Workflow-authored value to normalize.

    Returns:
        Value represented by the exact declared type. Missing supported values use the same USD type default as
        the property panel.

    Raises:
        TypeError: If the value cannot be represented by the declared type.
    """
    if value is None:
        usd_value_type = NATIVE_TYPE_TO_USD_VALUE_TYPE.get(native_type)
        value = usd_value_type.defaultValue if usd_value_type is not None else native_type()
        if isinstance(value, Sdf.AssetPath):
            value = pathlib.Path(value.path)
    elif native_type is pathlib.Path and type(value) is str:
        value = pathlib.Path(value)
    if native_type is pathlib.Path:
        value_matches_type = isinstance(value, pathlib.Path)
    else:
        value_matches_type = type(value) is native_type
    if not value_matches_type:
        raise TypeError(f"Workflow value must be {native_type.__name__}")
    return value
