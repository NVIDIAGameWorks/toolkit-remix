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
    "ComfyUIApplyReceipt",
    "ComfyUIApplyTarget",
    "ComfyUIAssetApplyTarget",
    "ComfyUIFileResult",
    "ComfyUIInputBinding",
    "ComfyUIWorkflowRequest",
    "MeshCandidate",
    "ReferenceTarget",
    "ResolverParameter",
    "ValueResolver",
    "Workflow",
    "WorkflowInput",
    "WorkflowOutput",
    "WorkflowTypeCategory",
    "WorkflowTypeOption",
]

import dataclasses
import pathlib
from copy import deepcopy
from typing import Any, Generic, TypeVar

from lightspeed.trex.asset_pipeline.core.metadata import MetadataApplyReceipt

import carb
from pxr import Sdf

from .enums import (
    OutputApplyBehavior,
    RemixType,
    WorkflowCategory,
    WorkflowSourceType,
    WorkflowType,
)
from .maps import OUTPUT_TEXTURE_TYPE_MAP, TYPE_MAP
from .preset import Preset
from .resolvers import (
    ConstantResolver,
    ResolverParameter,
    ValueResolver,
    create_default_resolver,
    create_resolver,
    normalize_native_value,
)

InputValueT = TypeVar("InputValueT")


def _validate_nonblank_string(field_name: str, value: object) -> str:
    """Validate one exact persisted identity string.

    Args:
        field_name: Field name used in validation errors.
        value: Persisted value to validate.

    Returns:
        The validated exact string.

    Raises:
        TypeError: If the value is not an exact string.
        ValueError: If the value is blank.
    """
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a str")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _validate_receipt_values(field_name: str, values: object, *, allow_empty: bool = False) -> set[str]:
    """Validate one exact receipt snapshot and return its target paths.

    Args:
        field_name: Snapshot field name used in validation errors.
        values: Persisted path-value tuples to validate.

    Returns:
        Unique shader-input paths described by the snapshot.

    Raises:
        TypeError: If the snapshot or an entry has the wrong exact type.
        ValueError: If paths are blank, invalid, duplicated, or the snapshot is empty.
    """
    if type(values) is not tuple:
        raise TypeError(f"{field_name} must be a tuple")
    if not values and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    paths = []
    for item in values:
        if type(item) is not tuple or len(item) != 2:
            raise TypeError(f"{field_name} entries must be path-value tuples")
        path, value = item
        if type(path) is not str:
            raise TypeError("receipt paths must be strings")
        if not path.strip():
            raise ValueError("receipt paths must not be blank")
        target_path = Sdf.Path(path)
        if not target_path.IsAbsolutePath() or not target_path.IsPropertyPath():
            raise ValueError("receipt paths must be absolute USD property paths")
        if value is not None and type(value) is not str:
            raise TypeError("receipt values must be strings or None")
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise ValueError(f"{field_name} paths must be unique")
    return set(paths)


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUIApplyTarget:
    """Identify the exact project layer and shader inputs changed by Apply.

    Attributes:
        context_name: USD context that owned the submitted material.
        project_path: Root layer identifier captured at submission.
        edit_target_layer: Edit layer identifier captured at submission.
        material_path: Material path used for user-facing validation errors.
        texture_targets: Stable workflow output keys paired with exact shader input paths.
    """

    context_name: str
    project_path: str
    edit_target_layer: str
    material_path: str
    texture_targets: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Validate the exact persisted project and shader-input identity.

        Raises:
            TypeError: If a persisted field has the wrong exact type or tuple shape.
            ValueError: If an identity is blank, duplicated, or not a valid absolute USD path.
        """
        if type(self.context_name) is not str:
            raise TypeError("context_name must be a str")
        _validate_nonblank_string("project_path", self.project_path)
        _validate_nonblank_string("edit_target_layer", self.edit_target_layer)
        _validate_nonblank_string("material_path", self.material_path)
        material_path = Sdf.Path(self.material_path)
        if not material_path.IsAbsolutePath() or not material_path.IsPrimPath():
            raise ValueError("material_path must be an absolute USD prim path")
        if type(self.texture_targets) is not tuple:
            raise TypeError("texture_targets must be a tuple")
        keys = []
        paths = []
        for item in self.texture_targets:
            if type(item) is not tuple or len(item) != 2:
                raise TypeError("texture_targets entries must be key-path tuples")
            key, path = item
            if type(key) is not str or type(path) is not str:
                raise TypeError("texture target keys and paths must be strings")
            if not key.strip() or not path.strip():
                raise ValueError("texture target keys and paths must not be blank")
            target_path = Sdf.Path(path)
            if not target_path.IsAbsolutePath() or not target_path.IsPropertyPath():
                raise ValueError("texture target paths must be absolute USD property paths")
            keys.append(key)
            paths.append(path)
        if len(keys) != len(set(keys)):
            raise ValueError("texture target keys must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("texture target paths must be unique")


@dataclasses.dataclass(frozen=True, slots=True)
class ReferenceTarget:
    """Identify one reference owner and the source reference that Replace removes."""

    owner_prim_path: str
    source_reference: Sdf.Reference | None
    source_layer_identifier: str | None

    def __post_init__(self) -> None:
        """Validate the exact owner and source identities."""
        _validate_nonblank_string("owner_prim_path", self.owner_prim_path)
        sdf_path = Sdf.Path(self.owner_prim_path)
        if not sdf_path.IsAbsolutePath() or not sdf_path.IsPrimPath():
            raise ValueError("owner_prim_path must be an absolute USD prim path")
        if self.source_reference is not None and not isinstance(self.source_reference, Sdf.Reference):
            raise TypeError("source_reference must be an Sdf.Reference or None")
        if self.source_layer_identifier is not None:
            _validate_nonblank_string("source_layer_identifier", self.source_layer_identifier)
        if (self.source_reference is None) is not (self.source_layer_identifier is None):
            raise ValueError("source reference and layer identifier must both be set or both be None")


@dataclasses.dataclass(frozen=True, slots=True)
class MeshCandidate:
    """Carry one URL-preserving model source and every stage owner that uses it.

    Attributes:
        source_path: Model URL, or ``None`` when the workflow has no mesh input.
        owners: Stage owners that receive the generated model. Empty for a processing-only Constant model.
        input_prim_path: Prim that the other workflow inputs resolve from when there is no owner.
        resolved_inputs: Input values, bindings, skip reason, and exclusion flag already resolved for this candidate.
    """

    source_path: str | None
    owners: tuple[ReferenceTarget, ...]
    input_prim_path: str | None = None
    resolved_inputs: tuple[dict[str, Any], tuple["ComfyUIInputBinding", ...], str | None, bool] | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUIAssetApplyTarget:
    """Identify the exact references and textures changed by one asset Apply."""

    context_name: str
    project_path: str
    edit_target_layer: str
    reference_targets: tuple[ReferenceTarget, ...]
    texture_targets: tuple[tuple[str, str], ...]
    mesh_apply_behavior: OutputApplyBehavior

    def __post_init__(self) -> None:
        """Validate one durable asset Apply target."""
        if type(self.context_name) is not str:
            raise TypeError("context_name must be a str")
        _validate_nonblank_string("project_path", self.project_path)
        _validate_nonblank_string("edit_target_layer", self.edit_target_layer)
        if type(self.reference_targets) is not tuple or not all(
            type(target) is ReferenceTarget for target in self.reference_targets
        ):
            raise TypeError("reference_targets must be a tuple of ReferenceTarget values")
        if type(self.texture_targets) is not tuple:
            raise TypeError("texture_targets must be a tuple")
        texture_paths = []
        for target in self.texture_targets:
            if type(target) is not tuple or len(target) != 2 or not all(type(value) is str for value in target):
                raise TypeError("texture_targets entries must be key-path string pairs")
            key, path = target
            if not key.strip() or not path.strip():
                raise ValueError("texture target keys and paths must not be blank")
            sdf_path = Sdf.Path(path)
            if not sdf_path.IsAbsolutePath() or not sdf_path.IsPropertyPath():
                raise ValueError("texture target paths must be absolute USD property paths")
            texture_paths.append(path)
        if len(texture_paths) != len(set(texture_paths)):
            raise ValueError("texture target paths must be unique")
        if type(self.mesh_apply_behavior) is not OutputApplyBehavior:
            raise TypeError("mesh_apply_behavior must be an OutputApplyBehavior")


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUIApplyReceipt:
    """Keep exact authored values separately from canonical comparison values.

    Attributes:
        original_authored_values: Shader inputs paired with their exact prior target-layer spellings.
        original_compare_values: Shader inputs paired with canonical prior values used for comparisons.
        applied_compare_values: Shader inputs paired with canonical values expected after Apply.
        metadata_receipt: Prior metadata sidecar content for every output.
    """

    original_authored_values: tuple[tuple[str, str | None], ...]
    original_compare_values: tuple[tuple[str, str | None], ...]
    applied_compare_values: tuple[tuple[str, str | None], ...]
    metadata_receipt: MetadataApplyReceipt

    def __post_init__(self) -> None:
        """Validate paired original and applied snapshots for one exact target set.

        All three snapshots may be empty together: a mesh-only receipt carries only the metadata receipt.

        Raises:
            TypeError: If a snapshot or path-value entry has the wrong exact type.
            ValueError: If paths are blank, invalid, duplicated, or differ between snapshots.
        """
        authored_paths = _validate_receipt_values(
            "original_authored_values", self.original_authored_values, allow_empty=True
        )
        original_paths = _validate_receipt_values(
            "original_compare_values", self.original_compare_values, allow_empty=True
        )
        applied_paths = _validate_receipt_values(
            "applied_compare_values", self.applied_compare_values, allow_empty=True
        )
        if type(self.metadata_receipt) is not MetadataApplyReceipt:
            raise TypeError("metadata_receipt must be a MetadataApplyReceipt")
        if authored_paths != original_paths or original_paths != applied_paths:
            raise ValueError("Apply receipt snapshots must describe the same paths")


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUIInputBinding:
    """Bind one semantic workflow port to one source file URL."""

    port_id: str
    remix_type: RemixType
    source: str

    def __post_init__(self) -> None:
        """Validate one persisted semantic input binding."""
        _validate_nonblank_string("port_id", self.port_id)
        if not isinstance(self.remix_type, RemixType) or self.remix_type not in {
            RemixType.TEXTURE_FILE_PATH,
            RemixType.MESH_FILE_PATH,
        }:
            raise ValueError("remix_type must identify a supported file input")
        _validate_nonblank_string("source", self.source)


@dataclasses.dataclass
class ComfyUIFileResult:
    """Describe one declared file output from a ComfyUI execution."""

    filename: str
    key: str
    remix_type: RemixType
    order: int = 0
    subfolder: str = ""
    texture_type: str | None = None
    path: pathlib.Path | None = None

    def __post_init__(self) -> None:
        """Validate one downloaded output descriptor."""
        _validate_nonblank_string("filename", self.filename)
        _validate_nonblank_string("key", self.key)
        if not isinstance(self.remix_type, RemixType) or self.remix_type not in {
            RemixType.TEXTURE_FILE_PATH,
            RemixType.MESH_FILE_PATH,
        }:
            raise ValueError("remix_type must identify a supported file output")
        if type(self.order) is not int:
            raise TypeError("order must be an int")
        if type(self.subfolder) is not str:
            raise TypeError("subfolder must be a str")
        if self.remix_type is RemixType.TEXTURE_FILE_PATH:
            if type(self.texture_type) is not str or self.texture_type not in OUTPUT_TEXTURE_TYPE_MAP:
                raise ValueError("texture_type must identify a supported texture output")
        elif self.texture_type is not None:
            raise ValueError("texture_type must be None for a mesh output")
        if self.path is not None and not isinstance(self.path, pathlib.Path):
            raise TypeError("path must be a pathlib.Path or None")


@dataclasses.dataclass
class WorkflowInput(Generic[InputValueT]):
    """A tagged workflow input parsed from rtx-remix metadata.

    Fields mirror the JSON structure from the ComfyUI rtx-remix API:

    - Top-level keys: ``name``, ``type``, ``remix_type``, ``order``
    - ``additional_data`` sub-keys promoted to fields: ``group``, ``tooltip``
    - Computed fields: ``port_id``, ``native_type``, ``value``
    """

    port_id: str
    label: str
    native_type: type
    default_value: InputValueT
    value: ValueResolver[InputValueT]
    order: int = 0
    remix_type: RemixType | None = None
    group: str = ""
    tooltip: str = ""

    def __post_init__(self) -> None:
        """Require every workflow input to own one explicit value resolver.

        Raises:
            TypeError: If ``value`` is not a value resolver.
        """
        if not isinstance(self.value, ValueResolver):
            raise TypeError("WorkflowInput.value must be a ValueResolver")

    @classmethod
    def from_dict(
        cls,
        node_id: str,
        port_name: str,
        raw: dict[str, Any],
        default_value: Any,
        context_name: str | None = None,
    ) -> "WorkflowInput | None":
        """Parse an rtx-remix input metadata entry and assign its default resolver.

        Args:
            node_id: ComfyUI node identifier that owns this input.
            port_name: Key in the node's ``inputs`` dict.
            raw: The rtx-remix metadata dict for this input port.
            default_value: Fallback value taken from the node's actual inputs.
            context_name: USD context semantic resolvers operate on.

        Returns:
            Parsed workflow input, or ``None`` when the metadata is malformed or unsupported.
        """
        if (
            not isinstance(node_id, str)
            or not node_id
            or "." in node_id
            or not isinstance(port_name, str)
            or not port_name
        ):
            carb.log_warn("Skipping malformed workflow input identity: node_id and port_name must be strings")
            return None
        if not isinstance(raw, dict):
            carb.log_warn(f"Skipping malformed metadata for input '{node_id}.{port_name}': expected dict")
            return None

        remix_type = None
        remix_type_str = raw.get("remix_type")
        if remix_type_str is not None:
            if not isinstance(remix_type_str, str):
                carb.log_warn(f"Skipping input '{node_id}.{port_name}': remix_type must be a string")
                return None
            try:
                remix_type = RemixType(remix_type_str)
            except ValueError:
                carb.log_warn(f"Skipping input '{node_id}.{port_name}': unknown remix_type '{remix_type_str}'")
                return None

        type_str = raw.get("type")
        if not isinstance(type_str, str) or type_str not in TYPE_MAP:
            carb.log_warn(f"Skipping input '{node_id}.{port_name}': missing rtx-remix input type")
            return None
        if remix_type in {RemixType.TEXTURE_FILE_PATH, RemixType.MESH_FILE_PATH}:
            native_type = pathlib.Path
        else:
            native_type = TYPE_MAP.get(type_str, str)
        try:
            value = create_default_resolver(remix_type, native_type, default_value, context_name)
        except TypeError:
            carb.log_warn(f"Skipping input '{node_id}.{port_name}': default value does not match type '{type_str}'")
            return None

        raw_additional_data = raw.get("additional_data", {})
        if not isinstance(raw_additional_data, dict):
            carb.log_warn(f"Skipping input '{node_id}.{port_name}': additional_data must be a dict")
            return None
        label = raw.get("name", port_name)
        order = raw.get("order", 0)
        group = raw_additional_data.get("group", "")
        tooltip = raw_additional_data.get("tooltip", "")
        if not isinstance(label, str):
            carb.log_warn(f"Skipping input '{node_id}.{port_name}': name must be a string")
            return None
        if not isinstance(order, int) or isinstance(order, bool):
            carb.log_warn(f"Skipping input '{node_id}.{port_name}': order must be an integer")
            return None
        if not isinstance(group, str) or not isinstance(tooltip, str):
            carb.log_warn(f"Skipping input '{node_id}.{port_name}': group and tooltip must be strings")
            return None

        return cls(
            port_id=f"{node_id}.inputs.{port_name}",
            label=label,
            native_type=native_type,
            default_value=default_value,
            value=value,
            order=order,
            remix_type=remix_type,
            group=group,
            tooltip=tooltip,
        )


@dataclasses.dataclass
class WorkflowOutput:
    """Describe one tagged workflow output and its persisted Apply settings."""

    node_id: str
    remix_type: RemixType
    order: int = 0
    texture_type: str | None = None
    apply_behavior: OutputApplyBehavior = OutputApplyBehavior.NONE
    name: str = ""
    group: str = ""

    def __post_init__(self) -> None:
        """Validate the output semantic and its permitted Apply settings."""
        _validate_nonblank_string("node_id", self.node_id)
        if "." in self.node_id:
            raise ValueError("node_id must not contain a dot")
        if type(self.remix_type) is not RemixType:
            raise TypeError("remix_type must be a RemixType")
        if type(self.order) is not int:
            raise TypeError("order must be an int")
        if type(self.apply_behavior) is not OutputApplyBehavior:
            raise TypeError("apply_behavior must be an OutputApplyBehavior")
        if type(self.name) is not str or type(self.group) is not str:
            raise TypeError("name and group must be str")
        if self.remix_type is RemixType.TEXTURE_FILE_PATH:
            if type(self.texture_type) is not str or self.texture_type not in OUTPUT_TEXTURE_TYPE_MAP:
                raise ValueError("texture_type must identify a supported texture output")
            if self.apply_behavior not in {OutputApplyBehavior.NONE, OutputApplyBehavior.REPLACE}:
                raise ValueError("texture outputs support Replace or Do Nothing")
        elif self.remix_type is RemixType.MESH_FILE_PATH:
            if self.texture_type is not None:
                raise ValueError("texture_type must be None for a mesh output")
        else:
            if self.texture_type is not None:
                raise ValueError("texture_type is supported only for texture outputs")
            if self.apply_behavior is not OutputApplyBehavior.NONE:
                raise ValueError("this output supports only Do Nothing")

    @classmethod
    def from_dict(cls, node_id: str, raw: dict[str, Any]) -> "WorkflowOutput | None":
        """Parse an rtx-remix workflow output metadata entry.

        Args:
            node_id: ComfyUI node identifier that owns the output.
            raw: Metadata dictionary describing the output.

        Returns:
            Parsed workflow output, or ``None`` when the metadata is malformed or unsupported.
        """
        if not isinstance(node_id, str) or not node_id.strip() or "." in node_id:
            carb.log_warn("Skipping malformed output metadata: node_id must be a non-blank string without dots")
            return None
        if not isinstance(raw, dict):
            carb.log_warn(f"Skipping malformed output metadata for node '{node_id}': expected dict")
            return None
        if "texture_type" in raw:
            carb.log_warn(
                f"Skipping malformed output metadata for node '{node_id}': texture_type belongs in additional_data"
            )
            return None
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            carb.log_warn(f"Skipping malformed output metadata for node '{node_id}': name must be a string")
            return None
        remix_type_value = raw.get("remix_type")
        if not isinstance(remix_type_value, str):
            carb.log_warn(f"Skipping malformed output metadata for node '{node_id}': remix_type must be a string")
            return None
        try:
            remix_type = RemixType(remix_type_value)
        except ValueError:
            carb.log_warn(
                f"Skipping unsupported output metadata for node '{node_id}': unknown remix_type '{remix_type_value}'"
            )
            return None
        additional = raw.get("additional_data", {})
        if not isinstance(additional, dict):
            carb.log_warn(f"Skipping malformed output metadata for node '{node_id}': additional_data must be a dict")
            return None
        order = raw.get("order", 0)
        if not isinstance(order, int) or isinstance(order, bool):
            carb.log_warn(f"Skipping malformed output metadata for node '{node_id}': order must be an integer")
            return None
        if remix_type in {RemixType.TEXTURE_FILE_PATH, RemixType.MESH_FILE_PATH} and raw.get("type") != "str":
            carb.log_warn(f"Skipping unsupported output metadata for node '{node_id}': type must be 'str'")
            return None
        group = additional.get("group", "")
        if not isinstance(group, str):
            carb.log_warn(f"Skipping malformed output metadata for node '{node_id}': group must be a string")
            return None
        if remix_type is RemixType.TEXTURE_FILE_PATH:
            texture_type = additional.get("texture_type")
            if not isinstance(texture_type, str) or texture_type not in OUTPUT_TEXTURE_TYPE_MAP:
                carb.log_warn(
                    f"Skipping malformed output metadata for node '{node_id}': "
                    "texture_type must identify a supported texture"
                )
                return None
            return cls(
                node_id=node_id,
                remix_type=remix_type,
                order=order,
                texture_type=texture_type,
                apply_behavior=OutputApplyBehavior.REPLACE,
                name=name,
                group=group,
            )
        if remix_type is RemixType.MESH_FILE_PATH:
            if "texture_type" in additional:
                carb.log_warn(
                    f"Skipping malformed output metadata for node '{node_id}': "
                    "mesh outputs must not declare texture_type"
                )
                return None
            return cls(
                node_id=node_id,
                remix_type=remix_type,
                order=order,
                apply_behavior=OutputApplyBehavior.REPLACE,
                name=name,
                group=group,
            )
        return cls(node_id=node_id, remix_type=remix_type, order=order, name=name, group=group)


def _get_workflow_remix_metadata(workflow_data: dict[str, Any]) -> dict[str, Any]:
    """Return workflow-level rtx-remix metadata from the full workflow.

    Args:
        workflow_data: Full LiteGraph workflow that may contain product metadata.

    Returns:
        Workflow-level rtx-remix metadata, or an empty dictionary when absent or malformed.
    """
    extra = workflow_data.get("extra")
    if isinstance(extra, dict):
        remix = extra.get("rtx-remix")
        if isinstance(remix, dict):
            return remix

    return {}


@dataclasses.dataclass
class Workflow:
    """ComfyUI workflow representation with input/output metadata and preset support."""

    api: dict[str, Any] = dataclasses.field(default_factory=dict)
    name: str = dataclasses.field(default="Workflow")
    source_type: WorkflowSourceType | None = None
    category: WorkflowCategory | None = None
    inputs: list[WorkflowInput] = dataclasses.field(default_factory=list)
    output_specs: list[WorkflowOutput] = dataclasses.field(default_factory=list)
    presets: dict[str, Preset] = dataclasses.field(default_factory=dict)
    active_preset: str | None = None
    group_order: list[str] = dataclasses.field(default_factory=list)
    workflow_defaults: dict[str, ValueResolver] = dataclasses.field(default_factory=dict)
    # Persisted Workflow payloads decode positionally: append new persisted fields at the end, after
    # workflow_type, and extend the codec's released-shape decoder.
    output_group_order: list[str] = dataclasses.field(default_factory=list)
    display_name: str = ""
    description: str = ""
    workflow_type: WorkflowType | None = None

    def __post_init__(self) -> None:
        """Fall back to the workflow name when no display name is set."""
        if not self.display_name:
            self.display_name = self.name

    @classmethod
    def from_catalog_entry(
        cls,
        category: WorkflowCategory,
        source_type: WorkflowSourceType,
        payload: dict[str, Any],
    ) -> "Workflow":
        """Create a catalog workflow from one entry of the node pack workflow list.

        Missing display metadata falls back to the workflow name for the display name and an
        empty description. The node pack owns the workflow type vocabulary; its value is its own
        label. An unknown or missing value reads as no type, so the workflow stays visible.

        Args:
            category: Workflow representation the entry belongs to.
            source_type: Where the workflow originates.
            payload: Raw catalog entry with a ``name`` and optional metadata.

        Returns:
            Catalog Workflow with resolved display metadata.

        Raises:
            TypeError: If the entry name is not a string.
            ValueError: If the entry name is blank.
        """
        name = payload.get("name")
        name = _validate_nonblank_string("name", name)
        raw_display_name = payload.get("displayName")
        display_name = raw_display_name if isinstance(raw_display_name, str) and raw_display_name.strip() else ""
        raw_description = payload.get("description")
        description = raw_description if isinstance(raw_description, str) else ""
        raw_type = payload.get("workflowType")
        workflow_type = None
        if isinstance(raw_type, str) and raw_type.strip():
            try:
                workflow_type = WorkflowType(raw_type)
            except ValueError:
                carb.log_warn(f"Workflow '{name}' has an unknown workflow type: {raw_type}")
        return cls(
            name=name,
            source_type=source_type,
            category=category,
            display_name=display_name,
            description=description,
            workflow_type=workflow_type,
        )

    def apply_preset(self, preset: Preset) -> None:
        """Build and commit one complete preset update.

        Workflow defaults are copied before validation. Omitted inputs return to their default resolver and value. An
        explicit preset value updates a default Constant resolver or replaces a semantic resolver with the input's
        canonical Constant resolver, so explicit preset authorship always wins without partial updates.

        Args:
            preset: A Preset instance with ``inputs`` mapping ``"node_id.port_name"`` to values.

        Raises:
            TypeError: If an override does not match its workflow input type.
            ValueError: If an override value is invalid for its resolver.
        """
        next_values = {
            workflow_input.port_id: deepcopy(self.workflow_defaults.get(workflow_input.port_id, workflow_input.value))
            for workflow_input in self.inputs
        }

        input_by_key = {}
        for workflow_input in self.inputs:
            parts = workflow_input.port_id.split(".")
            if len(parts) >= 3:
                port_name = ".".join(parts[2:])
                key = f"{parts[0]}.{port_name}"
                input_by_key[key] = workflow_input

        for key, override_value in preset.inputs.items():
            workflow_input = input_by_key.get(key)
            if workflow_input is None:
                continue
            normalized_value = normalize_native_value(workflow_input.native_type, override_value)
            next_value = next_values[workflow_input.port_id]
            if not isinstance(next_value, ConstantResolver):
                next_value = create_resolver(
                    ConstantResolver,
                    workflow_input.native_type,
                    workflow_input.default_value,
                )
                next_values[workflow_input.port_id] = next_value
            next_value.parameters[0].set_value(normalized_value)

        for workflow_input in self.inputs:
            workflow_input.value = next_values[workflow_input.port_id]

    def get_output_spec(self, node_id: str) -> WorkflowOutput | None:
        """Return the output spec for a node, or ``None`` if the node has no output.

        Args:
            node_id: ComfyUI node identifier to look up.

        Returns:
            Matching output specification, or ``None`` when the node declares no supported output.
        """
        for spec in self.output_specs:
            if spec.node_id == node_id:
                return spec
        return None

    @classmethod
    def _from_api(cls, data: dict[str, Any], name: str, context_name: str | None = None) -> "Workflow":
        """Create a workflow from the API half of a workflow pair.

        Args:
            data: API-format dict (node_id to node data with ``_meta.rtx-remix``).
            name: Display name for the workflow.
            context_name: USD context semantic resolvers operate on.

        Returns:
            Workflow containing all supported inputs and outputs parsed from the API data.
        """
        inputs: list[WorkflowInput] = []
        output_specs: list[WorkflowOutput] = []
        declares_mesh_input = False

        for node_id, node in data.items():
            if not isinstance(node_id, str) or not node_id:
                carb.log_warn("Skipping workflow node with malformed identifier")
                continue
            if not isinstance(node, dict):
                continue
            meta = node.get("_meta")
            if not meta:
                continue
            if not isinstance(meta, dict):
                carb.log_warn(f"Skipping malformed metadata for node '{node_id}': expected dict")
                continue
            remix = meta.get("rtx-remix")
            if not remix:
                continue
            if not isinstance(remix, dict):
                carb.log_warn(f"Skipping malformed rtx-remix metadata for node '{node_id}': expected dict")
                continue

            output = remix.get("output")
            if output:
                output_spec = WorkflowOutput.from_dict(node_id, output)
                if output_spec is not None:
                    output_specs.append(output_spec)

            remix_inputs = remix.get("inputs")
            if not remix_inputs:
                continue
            if not isinstance(remix_inputs, dict):
                carb.log_warn(f"Skipping malformed input metadata for node '{node_id}': expected dict")
                continue
            declares_mesh_input = declares_mesh_input or any(
                isinstance(raw_input, dict) and raw_input.get("remix_type") == RemixType.MESH_FILE_PATH
                for raw_input in remix_inputs.values()
            )

            node_inputs = node.get("inputs", {})
            if not isinstance(node_inputs, dict):
                carb.log_warn(f"Skipping rtx-remix inputs for node '{node_id}': node inputs are missing or malformed")
                continue

            for port_name, raw_input in remix_inputs.items():
                if port_name not in node_inputs:
                    carb.log_warn(f"Skipping input '{node_id}.{port_name}': port is missing from node inputs")
                    continue
                workflow_input = WorkflowInput.from_dict(
                    node_id,
                    port_name,
                    raw_input,
                    node_inputs[port_name],
                    context_name,
                )
                if workflow_input is not None:
                    inputs.append(workflow_input)

        # Replace needs a stage reference to replace. A text- or image-to-mesh workflow declares no mesh input, so
        # its generated model can only be added beside the selected prim. The declaration decides, not the parsed
        # inputs: a declared mesh input that failed to parse keeps Replace, and submission then rejects the workflow.
        if not declares_mesh_input:
            for output_spec in output_specs:
                if output_spec.remix_type is RemixType.MESH_FILE_PATH:
                    output_spec.apply_behavior = OutputApplyBehavior.APPEND
        return cls(api=data, name=name, inputs=inputs, output_specs=output_specs)

    @classmethod
    def from_litegraph_dict(
        cls,
        api_workflow: dict[str, Any],
        full_workflow: dict[str, Any],
        name: str = "Workflow",
        context_name: str | None = None,
    ) -> "Workflow":
        """Create a Workflow from API and full workflow data.

        Inputs and outputs are parsed from ``api_workflow`` (the execution
        format). Presets, groupOrder, and activePreset are extracted from
        ``full_workflow`` (the LiteGraph format) under ``extra.rtx-remix``.

        Args:
            api_workflow: API-format dict (node_id to inputs) for execution.
            full_workflow: Full LiteGraph dict with ``extra`` metadata.
            name: Display name for the workflow.
            context_name: USD context semantic resolvers operate on.

        Returns:
            Workflow containing parsed execution metadata, presets, and group ordering.
        """
        workflow = cls._from_api(data=api_workflow, name=name, context_name=context_name)

        # Store defaults before any preset is applied
        workflow.workflow_defaults = deepcopy({inp.port_id: inp.value for inp in workflow.inputs})

        remix_meta = _get_workflow_remix_metadata(full_workflow)

        # Parse presets
        raw_presets = remix_meta.get("presets", {})
        if not isinstance(raw_presets, dict):
            carb.log_warn("Ignoring malformed workflow presets: expected dict")
            raw_presets = {}
        for preset_name, preset_data in raw_presets.items():
            preset = Preset.from_dict(preset_name, preset_data)
            if preset is not None:
                workflow.presets[preset_name] = preset

        # Parse group ordering. Inputs and outputs keep separate lists.
        for key, attribute in (("groupOrder", "group_order"), ("outputGroupOrder", "output_group_order")):
            order = remix_meta.get(key, [])
            if isinstance(order, list) and all(isinstance(group, str) for group in order):
                setattr(workflow, attribute, order)
            elif order:
                carb.log_warn(f"Ignoring malformed workflow {key}: expected a list of strings")

        # Apply only the workflow author's explicit selection.
        active = remix_meta.get("activePreset")
        if active is not None and not isinstance(active, str):
            carb.log_warn("Ignoring malformed workflow activePreset: expected string")
            active = None
        if active in workflow.presets:
            workflow.active_preset = active
            workflow.apply_preset(workflow.presets[active])

        return workflow


def _parse_workflow_type_options(raw: Any) -> list["WorkflowTypeOption"]:
    """Parse the ``types`` list of one category from the ``workflows/types`` endpoint.

    The node pack owns the workflow type vocabulary. A value that this build cannot map to a
    ``WorkflowType`` member, a blank value, or a malformed entry is skipped and logged: adding
    it as a filter would match no workflow, and the workflows that carry it stay visible
    under "All".

    Args:
        raw: Decoded ``types`` value for one category.

    Returns:
        Parsed type options in the order the server published them.
    """
    if not isinstance(raw, list):
        return []
    options: list[WorkflowTypeOption] = []
    for entry in raw:
        if not isinstance(entry, dict):
            carb.log_warn(f"Skipping malformed workflow type entry published by the server: {entry!r}")
            continue
        value = entry.get("value")
        if not isinstance(value, str) or not value:
            carb.log_warn(f"Skipping unusable workflow type value published by the server: {value!r}")
            continue
        try:
            workflow_type = WorkflowType(value)
        except ValueError:
            carb.log_warn(f"Skipping unknown workflow type published by the server: {value!r}")
            continue
        description = entry.get("description")
        if not isinstance(description, str):
            description = ""
        options.append(WorkflowTypeOption(workflow_type=workflow_type, description=description))
    return options


@dataclasses.dataclass
class WorkflowTypeOption:
    """One workflow type of the vocabulary of the server, with the description that the server publishes."""

    workflow_type: WorkflowType
    description: str = ""


@dataclasses.dataclass
class WorkflowTypeCategory:
    """One category of workflow types, in the display order of the server."""

    name: str
    types: tuple[WorkflowTypeOption, ...] = ()

    @classmethod
    def list_from_payload(cls, payload: Any) -> list["WorkflowTypeCategory"]:
        """Parse the ``categories`` list of the ``workflows/types`` endpoint.

        Args:
            payload: Decoded ``categories`` value from the endpoint response.

        Returns:
            Parsed categories in the order the server published them, or an empty list when
            the payload is not a list of category dictionaries.
        """
        if not isinstance(payload, list):
            return []
        categories: list[WorkflowTypeCategory] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            categories.append(cls(name=name, types=tuple(_parse_workflow_type_options(entry.get("types")))))
        return categories


@dataclasses.dataclass(frozen=True, slots=True)
class ComfyUIWorkflowRequest:
    """Carry one resolved ComfyUI workflow invocation through a typed job input.

    Attributes:
        prompt: Resolved API-format workflow submitted to ComfyUI.
        input_bindings: Semantic workflow file bindings uploaded before submission.
        client_id: ComfyUI client identifier stored with the submitted prompt.
        timeout: Maximum seconds to wait for the submitted prompt.
        output_url: Project-owned destination, or ``None`` for queue-owned project-independent outputs.
        workflow: Complete workflow metadata used to validate outputs and reopen the editor.
    """

    prompt: dict[str, Any]
    input_bindings: tuple[ComfyUIInputBinding, ...]
    client_id: str
    timeout: float
    output_url: str | None
    workflow: Workflow

    def __post_init__(self) -> None:
        """Validate the exact persisted request shape.

        Raises:
            TypeError: If a field has the wrong concrete type.
            ValueError: If a required string is blank, a port repeats, or the timeout is not positive.
        """
        if type(self.prompt) is not dict:
            raise TypeError("prompt must be a dictionary")
        if type(self.input_bindings) is not tuple or not all(
            type(binding) is ComfyUIInputBinding for binding in self.input_bindings
        ):
            raise TypeError("input_bindings must be a tuple of ComfyUIInputBinding values")
        ports: set[str] = set()
        for binding in self.input_bindings:
            if binding.port_id in ports:
                raise ValueError(f"Workflow input port is bound more than once: {binding.port_id}")
            ports.add(binding.port_id)
        if type(self.client_id) is not str:
            raise TypeError("client_id must be a string")
        if type(self.timeout) is not float:
            raise TypeError("timeout must be a float")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.output_url is not None and type(self.output_url) is not str:
            raise TypeError("output_url must be a string or None")
        if self.output_url is not None and not self.output_url.strip():
            raise ValueError("output_url must be non-empty")
        if type(self.workflow) is not Workflow:
            raise TypeError("workflow must be a Workflow")
