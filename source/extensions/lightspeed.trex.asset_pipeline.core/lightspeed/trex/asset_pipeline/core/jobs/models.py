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

__all__ = [
    "LineageEntry",
    "MeshOptimizationRequest",
    "MeshOptimizationResult",
    "PrepareOptimizationResult",
    "ProcessedTexture",
    "TextureLedgerEntry",
    "TextureProcessingItem",
    "TextureProcessingRequest",
    "TextureProcessingResult",
    "derive_texture_key",
    "resolve_processed_textures",
]

import pathlib
from collections.abc import Iterable
from dataclasses import dataclass

from omni.flux.asset_importer.core.data_models import TextureTypes

from ..pipeline.item import TextureAsset


def _validate_texture_fields(key: str, path: pathlib.Path, texture_type: TextureTypes) -> None:
    """Validate fields shared by source and processed texture records.

    Args:
        key: Stable caller-defined item identifier.
        path: Local source path identifying the asset.
        texture_type: Required texture semantic.

    Raises:
        TypeError: If any field has an invalid type.
        ValueError: If the key is blank.
    """
    if type(key) is not str:
        raise TypeError("key must be a str")
    if not key.strip():
        raise ValueError("key must not be blank")
    if not isinstance(path, pathlib.Path):
        raise TypeError("path must be a pathlib.Path")
    if not isinstance(texture_type, TextureTypes):
        raise TypeError("texture_type must be a TextureTypes value")


@dataclass(frozen=True, slots=True)
class TextureProcessingItem:
    """Describe one local source texture and its required Remix semantic.

    Attributes:
        key: Stable caller-defined identifier preserved through processing.
        path: Local source path consumed by the Remix texture pipeline.
        texture_type: Required texture semantic.
    """

    key: str
    path: pathlib.Path
    texture_type: TextureTypes

    def __post_init__(self) -> None:
        """Validate the persisted texture boundary.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If the stable key is blank.
        """
        _validate_texture_fields(self.key, self.path, self.texture_type)


@dataclass(frozen=True, slots=True)
class TextureProcessingRequest:
    """Provide one ordered texture batch and its publication destination.

    Attributes:
        items: Local source textures in stable caller order.
        source_root: Stable project or import root preserved in output paths.
        output_url: Explicit local or remote destination, or ``None`` to keep outputs in the job directory.
    """

    items: tuple[TextureProcessingItem, ...]
    source_root: pathlib.Path
    output_url: str | None

    def __post_init__(self) -> None:
        """Validate the persisted request boundary.

        Raises:
            TypeError: If request fields do not have their exact persisted types.
            ValueError: If the explicit publication URL is blank.
        """
        if type(self.items) is not tuple or not all(type(item) is TextureProcessingItem for item in self.items):
            raise TypeError("items must be a tuple of TextureProcessingItem values")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("item keys must be unique within one request")
        if not isinstance(self.source_root, pathlib.Path):
            raise TypeError("source_root must be a pathlib.Path")
        if self.output_url is not None and type(self.output_url) is not str:
            raise TypeError("output_url must be a str or None")
        if self.output_url is not None and not self.output_url.strip():
            raise ValueError("output_url must not be blank")


@dataclass(frozen=True, slots=True)
class ProcessedTexture:
    """Identify one source texture and its final published output.

    Attributes:
        key: Stable caller-defined identifier preserved from the source request.
        source_path: Original local source path used for stable correlation.
        asset_url: Final local path or remote URL safe to pass to Apply handlers.
        texture_type: Final texture semantic after processing.
        udim_tiles: Published asset URLs of every concrete UDIM tile in sequence order, or an empty
            tuple for a non-UDIM texture.
    """

    key: str
    source_path: pathlib.Path
    asset_url: str
    texture_type: TextureTypes
    udim_tiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the immutable processed-texture boundary.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If the stable key or URL is blank.
        """
        _validate_texture_fields(self.key, self.source_path, self.texture_type)
        if type(self.asset_url) is not str:
            raise TypeError("asset_url must be a str")
        if type(self.udim_tiles) is not tuple or not all(type(tile) is str for tile in self.udim_tiles):
            raise TypeError("udim_tiles must be a tuple of str values")
        if not self.asset_url.strip():
            raise ValueError("asset_url must not be blank")


#: One published asset: its source path, its output path, and the hash of the source. The alias keeps
#: the wire format a plain tuple, which the persistence codecs match on exact type.
LineageEntry = tuple[str, str, str]


def _validate_lineage(lineage: tuple) -> None:
    """Validate every entry is a 3-tuple of str with no blank element; raise TypeError or ValueError."""
    if type(lineage) is not tuple:
        raise TypeError("lineage must be a tuple of (source_path, output_path, source_hash) entries")
    for i, entry in enumerate(lineage):
        if type(entry) is not tuple or len(entry) != 3 or not all(type(e) is str for e in entry):
            raise TypeError(f"lineage[{i}] must be a 3-tuple of str, got {type(entry).__name__}")
        if not entry[0].strip() or not entry[1].strip() or not entry[2].strip():
            raise ValueError(f"lineage[{i}] elements must not be blank")


@dataclass(frozen=True, slots=True)
class TextureProcessingResult:
    """Contain immutable processed textures in their original request order.

    Attributes:
        items: Fully published textures safe for downstream Apply bindings.
        lineage: One lineage entry per published texture, in request order. Each entry is a
            ``(source_path, output_path, source_hash)`` triple; ``source_path`` may be synthetic
            for a texture that an import materialized, and ``source_hash`` is never blank because
            the database column is NOT NULL.
        validation_passed: Whether the producing pipeline recorded no step errors.
    """

    items: tuple[ProcessedTexture, ...]
    lineage: tuple[LineageEntry, ...] = ()
    validation_passed: bool = True

    def __post_init__(self) -> None:
        """Validate the exact persisted result shape.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If item keys are duplicated.
        """
        if type(self.items) is not tuple or not all(type(item) is ProcessedTexture for item in self.items):
            raise TypeError("items must be a tuple of ProcessedTexture values")
        _validate_lineage(self.lineage)
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("item keys must be unique within one result")

    def rebased_onto(self, textures: Iterable[TextureAsset]) -> TextureProcessingResult:
        """Return this result with every URL pointing at the copy published for the same key.

        A model job publishes the textures it binds beside the model and refers to those copies, so the
        terminal result must name them for the Apply handler to write metadata on the files the model
        references. An item whose key has no published copy keeps its current location.

        Args:
            textures: Final texture records of the published model, matched by processed-texture key.

        Returns:
            A result with the same keys, semantics, hashes, and validation state.
        """
        published_by_key = {texture.key: texture for texture in textures}
        url_map: dict[str, str] = {}
        items = []
        for item in self.items:
            published = published_by_key.get(item.key)
            if published is None:
                items.append(item)
                continue
            url_map[item.asset_url] = str(published.path)
            items.append(
                ProcessedTexture(
                    key=item.key,
                    source_path=item.source_path,
                    asset_url=str(published.path),
                    texture_type=item.texture_type,
                    udim_tiles=tuple(str(tile) for tile in published.udim_tiles),
                )
            )
        lineage = tuple(
            (source_path, url_map.get(output_url, output_url), source_hash)
            for source_path, output_url, source_hash in self.lineage
        )
        return TextureProcessingResult(items=tuple(items), lineage=lineage, validation_passed=self.validation_passed)


@dataclass(frozen=True, slots=True)
class MeshOptimizationRequest:
    """Describe one local source model consumed by the mesh-optimization job.

    Attributes:
        source_path: Local source model consumed by the Remix model pipeline.
        source_root: Stable project or import root preserved in output paths.
        output_url: Explicit local or remote destination, or ``None`` to keep outputs in the job directory.
        replace_udim_textures_by_empty: Author an empty shader attribute for UDIM textures instead
            of a ``<UDIM>`` token. Model ingestion sets this to ``True``.
    """

    source_path: pathlib.Path
    source_root: pathlib.Path
    output_url: str | None = None
    replace_udim_textures_by_empty: bool = True

    def __post_init__(self) -> None:
        """Validate the persisted request boundary.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If the explicit publication URL is blank.
        """
        if not isinstance(self.source_path, pathlib.Path):
            raise TypeError("source_path must be a pathlib.Path")
        if not isinstance(self.source_root, pathlib.Path):
            raise TypeError("source_root must be a pathlib.Path")
        if self.output_url is not None and type(self.output_url) is not str:
            raise TypeError("output_url must be a str or None")
        if self.output_url is not None and not self.output_url.strip():
            raise ValueError("output_url must not be blank")


@dataclass(frozen=True, slots=True)
class MeshOptimizationResult:
    """Identify the final published model and the processed textures published beside it.

    Attributes:
        asset_url: Final local path or remote URL of the published model USD.
        texture_result: Processed textures as published beside the model, which is where the model
            refers to them. The terminal Apply handler writes their metadata sidecars there; the texture
            job carries no Apply binding of its own in a model graph, and its own outputs are a handoff
            inside the queue.
        lineage: Complete lineage of every asset the pipeline consumed and published: the model itself,
            every sub-USD layer published alongside it, and every texture entry from ``texture_result``.
            Each entry is a ``(source_path, output_path, source_hash)`` triple. A consumer needs no
            other source of truth and must never walk USD itself.
        source_path: Local source model path consumed by the pipeline; ``None`` when unknown.
        validation_passed: Whether the producing pipeline recorded no step errors.
    """

    asset_url: str
    texture_result: TextureProcessingResult
    lineage: tuple[LineageEntry, ...] = ()
    source_path: pathlib.Path | None = None
    validation_passed: bool = True

    def __post_init__(self) -> None:
        """Validate the immutable optimized-mesh boundary.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If the asset URL is blank.
        """
        if type(self.asset_url) is not str:
            raise TypeError("asset_url must be a str")
        if not self.asset_url.strip():
            raise ValueError("asset_url must not be blank")
        if type(self.texture_result) is not TextureProcessingResult:
            raise TypeError("texture_result must be a TextureProcessingResult")
        _validate_lineage(self.lineage)


@dataclass(frozen=True, slots=True)
class TextureLedgerEntry:
    """Record one texture binding discovered from the model stage.

    The pair ``(material_path, texture_type)`` is the identity that survives both phases. The mesh
    phase converts each material's shader between the two stage walks, so a shader prim path is not
    stable. The material prim path is, and a material carries at most one texture per semantic. A
    source path is not stable either, because a non-USD import synthesizes a new one each time.

    Attributes:
        material_path: Stable material prim path that owns the texture binding.
        texture_type: Texture semantic bound under that material.
        texture_key: Key matching the :class:`TextureProcessingItem` and :class:`ProcessedTexture`
            that owns this binding's converted output.
    """

    material_path: str
    texture_type: TextureTypes
    texture_key: str

    def __post_init__(self) -> None:
        """Validate the exact ledger entry types.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If a string field is blank.
        """
        if type(self.material_path) is not str:
            raise TypeError("material_path must be a str")
        if not self.material_path.strip():
            raise ValueError("material_path must not be blank")
        if type(self.texture_type) is not TextureTypes:
            raise TypeError("texture_type must be a TextureTypes value")
        if type(self.texture_key) is not str:
            raise TypeError("texture_key must be a str")
        if not self.texture_key.strip():
            raise ValueError("texture_key must not be blank")


def derive_texture_key(material_path: str, texture_type: TextureTypes) -> str:
    """Return the deterministic processing key for one material texture binding.

    Both stage walks derive the same key from the same identity, so the prepare phase and the mesh
    phase agree without any positional counter.

    Args:
        material_path: Material prim path that owns the binding.
        texture_type: Texture semantic bound under that material.

    Returns:
        A key unique to the identity within one model.
    """
    return f"{material_path}:{texture_type.name}"


def resolve_processed_textures(
    texture_ledger: tuple[TextureLedgerEntry, ...],
    texture_result: TextureProcessingResult,
) -> dict[tuple[str, TextureTypes], ProcessedTexture]:
    """Build the identity-to-processed-texture map validated against the ledger.

    Every ledger entry's ``texture_key`` must have a matching ``ProcessedTexture`` in the result.
    Two ledger entries that assign different keys to the same ``(material_path, texture_type)``
    identity are detected here, so the application step can do a single direct lookup.

    Args:
        texture_ledger: Every texture binding discovered in the prepare phase.
        texture_result: Immutable outputs from the texture-processing phase.

    Returns:
        Map from ``(material_path, texture_type)`` to the resolved ``ProcessedTexture``.

    Raises:
        ValueError: If a ledger entry names a texture key with no processed output, or if
            two ledger entries assign different keys to the same
            ``(material_path, texture_type)`` identity.
    """
    processed_by_key: dict[str, ProcessedTexture] = {item.key: item for item in texture_result.items}
    result: dict[tuple[str, TextureTypes], ProcessedTexture] = {}
    for entry in texture_ledger:
        if entry.texture_key not in processed_by_key:
            raise ValueError(
                f"Ledger entry for material {entry.material_path} texture type "
                f"{entry.texture_type.name} references texture key {entry.texture_key!r} "
                f"which has no matching processed texture"
            )
        # Two materials that share one file resolve to the same key, so a repeated identity is
        # only a conflict when it disagrees about which key owns it.
        identity = (entry.material_path, entry.texture_type)
        existing = result.get(identity)
        if existing is not None and existing.key != entry.texture_key:
            raise ValueError(
                f"Conflicting ledger entries for material {entry.material_path} texture type "
                f"{entry.texture_type.name}: {existing.key!r} and {entry.texture_key!r}"
            )
        result[identity] = processed_by_key[entry.texture_key]
    return result


@dataclass(frozen=True, slots=True)
class PrepareOptimizationResult:
    """Carry the discovered model and texture state to downstream optimization jobs.

    Attributes:
        model_work_path: Published intermediate USD produced by the standardize-input step.
        texture_items: Discovered texture records consumed by the texture-processing phase.
        source_path: Original model source path that drives the final output location.
        source_root: Stable project or import root preserved in output paths.
        referenced_layers: Every composed layer identifier, recorded by DiscoverTexturesStep.
        texture_ledger: Every shader binding discovered, keyed by ``(material_path, texture_type)`` so the
            mesh phase can match processed textures after material conversion rewrites the shader prims.
        output_url: Explicit local or remote destination, or ``None`` to keep outputs in the job directory.
        replace_udim_textures_by_empty: Author an empty shader attribute for UDIM textures instead of
            a ``<UDIM>`` token. Carried from the source request through the prepare phase.
    """

    model_work_path: pathlib.Path
    texture_items: tuple[TextureProcessingItem, ...]
    source_path: pathlib.Path
    source_root: pathlib.Path
    referenced_layers: tuple[str, ...]
    texture_ledger: tuple[TextureLedgerEntry, ...]
    output_url: str | None = None
    replace_udim_textures_by_empty: bool = True

    def __post_init__(self) -> None:
        """Validate the exact persisted result shape.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If texture items violate invariants or the explicit publication URL is blank.
        """
        if not isinstance(self.model_work_path, pathlib.Path):
            raise TypeError("model_work_path must be a pathlib.Path")
        if type(self.texture_items) is not tuple or not all(
            type(item) is TextureProcessingItem for item in self.texture_items
        ):
            raise TypeError("texture_items must be a tuple of TextureProcessingItem values")
        if len({item.key for item in self.texture_items}) != len(self.texture_items):
            raise ValueError("texture item keys must be unique within one result")
        if type(self.referenced_layers) is not tuple or not all(
            isinstance(layer, str) for layer in self.referenced_layers
        ):
            raise TypeError("referenced_layers must be a tuple of str values")
        if not isinstance(self.source_path, pathlib.Path):
            raise TypeError("source_path must be a pathlib.Path")
        if not isinstance(self.source_root, pathlib.Path):
            raise TypeError("source_root must be a pathlib.Path")
        if self.output_url is not None and type(self.output_url) is not str:
            raise TypeError("output_url must be a str or None")
        if self.output_url is not None and not self.output_url.strip():
            raise ValueError("output_url must not be blank")
        if type(self.texture_ledger) is not tuple or not all(
            type(entry) is TextureLedgerEntry for entry in self.texture_ledger
        ):
            raise TypeError("texture_ledger must be a tuple of TextureLedgerEntry values")
