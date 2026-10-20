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

__all__ = ("AttributeCopyPasteHelper",)

import json
from enum import Enum
from typing import Protocol, runtime_checkable

import carb
import omni.kit.clipboard
import omni.kit.undo
import omni.usd
from pxr import Sdf


@runtime_checkable
class _UsdRow(Protocol):
    """Existing USD row data, without importing its concrete extension."""

    attribute_paths: list[Sdf.Path]
    context_name: str
    metadata_key: str | None


class AttributeCopyPasteHelper:
    """Clipboard ownership for property rows; models retain editing policy."""

    @staticmethod
    def _encode(value):
        """Encode a native value for JSON, normalizing asset path separators.

        Raises:
            TypeError: If the value has no supported JSON representation.
        """
        if isinstance(value, Sdf.AssetPath):
            return {"_key": "pxr.Sdf.AssetPath", "_value": value.path.replace("\\", "/")}
        if isinstance(value, Enum):
            return value.value
        # Native vectors and arrays become JSON sequences without changing their order.
        try:
            return list(value)
        except TypeError as error:
            raise TypeError(f"Unsupported property value: {type(value).__name__}") from error

    @classmethod
    def _decode(cls, value):
        """Decode native values from JSON containers.

        Raises:
            ValueError: If a typed record is unsupported or malformed.
        """
        if isinstance(value, list):
            return [cls._decode(component) for component in value]
        if not isinstance(value, dict):
            return value
        if "_key" not in value:
            return {key: cls._decode(component) for key, component in value.items()}
        if set(value) != {"_key", "_value"} or value["_key"] != "pxr.Sdf.AssetPath":
            raise ValueError("Unsupported serialized property type")
        if not isinstance(value["_value"], str):
            raise ValueError("Invalid serialized asset path")
        return Sdf.AssetPath(value["_value"])

    @staticmethod
    def _properties(row):
        """Return canonical identities and backing attributes, or reject the row."""
        if row.read_only:
            return []
        names = row.get_logical_row_attribute_names()
        if names is not None:
            stage = omni.usd.get_context(row.context_name).get_stage()
            if not stage:
                return []
            targets = row.get_target_paths()
            attributes = [
                [stage.GetAttributeAtPath(Sdf.Path(target).AppendProperty(name)) for target in targets]
                for name in names
            ]
            if not targets or any(not attribute for group in attributes for attribute in group):
                return []
            return [((name, None), group[-1]) for name, group in zip(names, attributes)]
        if isinstance(row, _UsdRow):
            stage = omni.usd.get_context(row.context_name).get_stage()
            if not stage or not row.attribute_paths:
                return []
            attributes = [stage.GetAttributeAtPath(path) for path in row.attribute_paths]
            if all(attributes):
                return [((row.attribute_paths[-1].name, row.metadata_key), attributes[-1])]
            if all(stage.GetRelationshipAtPath(path) for path in row.attribute_paths):
                return [((tuple(model.get_value() for model in row.name_models), None), None)]
            if not all(model.is_virtual for model in row.value_models):
                return []
            if not all(stage.GetPrimAtPath(path.GetPrimPath()) for path in row.attribute_paths):
                return []
            return [((row.attribute_paths[-1].name, row.metadata_key), attributes[-1])]
        return [((tuple(model.get_value() for model in row.name_models), None), None)]

    @classmethod
    def copy(cls, *, source_rows) -> None:
        """Copy eligible rows using property identities rather than source prim paths."""
        data = []
        for row in source_rows:
            properties = cls._properties(row)
            if not properties:
                continue
            records = []
            logical = row.get_logical_row_attribute_names() is not None
            for (name, metadata_key), attribute in properties:
                if logical:
                    value = attribute.Get()
                elif isinstance(name, tuple):
                    value = [model.get_value() for model in row.value_models]
                elif metadata_key:
                    value = attribute.GetMetadata(metadata_key) if attribute else None
                    if value is None:
                        value = row.value_models[0].default_value
                elif attribute and attribute.GetTypeName() == Sdf.ValueTypeNames.Asset:
                    value = row.value_models[0].get_attributes_raw_value(-1)
                else:
                    # Virtual defaults and label-based choices already have model-facing values.
                    values = []
                    for model in row.value_models:
                        model.refresh()
                        values.append(
                            model.get_attributes_raw_value(-1)
                            if not attribute or (model.is_virtual and attribute.Get() is None)
                            else model.get_value()
                        )
                    value = values[0] if len(values) == 1 else values
                record = {"name": name, "value": value}
                if metadata_key is not None:
                    record["metadata_key"] = metadata_key
                records.append(record)
            data.append({"properties": records})
        omni.kit.clipboard.copy(json.dumps(data, default=cls._encode))

    @classmethod
    def _read(cls):
        """Read clipboard data, rejecting rows with malformed or duplicate records."""
        try:
            data = json.loads(omni.kit.clipboard.paste())
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        rows = []
        for row in data:
            if not isinstance(row, dict) or set(row) != {"properties"} or not isinstance(row["properties"], list):
                continue
            records = {}
            for record in row["properties"]:
                if not isinstance(record, dict) or not {"name", "value"} <= record.keys():
                    break
                if record.keys() - {"name", "value", "metadata_key"}:
                    break
                name = record["name"]
                key = record.get("metadata_key")
                if isinstance(name, list) and name and all(isinstance(part, str) for part in name):
                    name = tuple(name)
                elif not isinstance(name, str) or not name:
                    break
                if key is not None and (not isinstance(key, str) or not key):
                    break
                identity = (name, key)
                if identity in records:
                    break
                try:
                    records[identity] = cls._decode(record["value"])
                except ValueError:
                    break
            else:
                if records:
                    rows.append(records)
        return rows

    @classmethod
    def _prepare(cls, rows, data):
        """Prepare eligible rows without invoking their setters.

        Yields:
            Pairs of destination rows and value tuples in their canonical order.
        """
        for row in rows:
            properties = cls._properties(row)
            identities = [identity for identity, _ in properties]
            if not identities:
                continue
            for records in data:
                if set(records) != set(identities):
                    continue
                if row.get_logical_row_attribute_names() is not None:
                    yield row, tuple(records[identity] for identity in identities)
                    break
                value = records[identities[0]]
                if isinstance(identities[0][0], tuple) or len(row.value_models) > 1:
                    if not isinstance(value, (list, tuple)) or len(value) != len(row.value_models):
                        continue
                    values = tuple(value)
                else:
                    values = (value,)
                prepared = []
                for model, incoming in zip(row.value_models, values):
                    value = incoming.path if isinstance(incoming, Sdf.AssetPath) else incoming
                    if isinstance(incoming, Sdf.AssetPath) and isinstance(row, _UsdRow):
                        value = omni.usd.make_path_relative_to_current_edit_target(
                            value, stage=omni.usd.get_context(row.context_name).get_stage()
                        )
                    current = model.get_value()
                    if isinstance(current, Enum):
                        try:
                            value = type(current)(value)
                        except ValueError:
                            break
                    prepared.append(value)
                else:
                    yield row, tuple(prepared)
                    break

    @classmethod
    def can_paste(cls, *, target_rows) -> bool:
        """Check clipboard structure and row eligibility without invoking setters."""
        return next(cls._prepare(target_rows, cls._read()), None) is not None

    @classmethod
    def paste(cls, *, target_rows) -> None:
        """Group synchronous row edits. Existing callbacks own any delayed writes."""
        prepared_rows = list(cls._prepare(target_rows, cls._read()))
        if not prepared_rows:
            carb.log_warn("No matching editable property rows in clipboard data")
            return
        with omni.kit.undo.group(remove_if_empty=True):
            for row, values in prepared_rows:
                row.set_linked_edit_enabled(False)
                row.set_row_values(values)
