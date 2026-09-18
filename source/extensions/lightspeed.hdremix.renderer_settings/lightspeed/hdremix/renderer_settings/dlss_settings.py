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
    "DLSS_ADVANCED_SETTINGS",
    "DLSS_AUTO_MASK",
    "DLSS_CHARACTER_INTENSITY",
    "DLSS_ENABLE",
    "DLSS_FLOAT4_RANGE",
    "DLSS_HIGHLIGHT_RECOVERY",
    "DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS",
    "DLSS_INTENSITY",
    "DLSS_MAIN_SETTINGS",
    "DLSS_MODEL",
    "DLSS_SETTINGS",
    "DLSS_SETTINGS_TITLE",
    "DLSS_STRUCTURE_INTENSITY",
    "DLSS_TONE_INTENSITY",
    "DLSS_UNIT_FLOAT_RANGE",
    "DLSS_VOLUMETRIC_IMPROVEMENT",
    "SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE",
    "DlssSetting",
    "DlssSettingKind",
    "coerce_dlss_value",
    "format_dlss_value",
]

import math
from dataclasses import dataclass
from enum import Enum


class DlssSettingKind(Enum):
    """Supported DLSS Neural Rendering setting value shapes."""

    BOOL = "bool"
    ENUM = "enum"
    UNIT_FLOAT = "unit_float"
    FLOAT4 = "float4"


_DlssDefault = bool | int | float | tuple[float, float, float, float]
_DlssValue = bool | int | float | list[float]


@dataclass(frozen=True)
class DlssSetting:
    """Describe one persistent Toolkit setting and its runtime option."""

    identifier: str
    setting_path: str
    runtime_key: str
    default: _DlssDefault
    label: str
    tooltip: str
    kind: DlssSettingKind
    options: tuple[str, ...] = ()


_SETTING_PREFIX = "/persistent/exts/lightspeed.hdremix.renderer_settings"
_RUNTIME_PREFIX = "rtx.dlssNeuralRendering"
DLSS_SETTINGS_TITLE = "DLSS 3D-Guided Neural Generation [Experimental]"
DLSS_UNIT_FLOAT_RANGE = (0.0, 1.0)
DLSS_FLOAT4_RANGE = (0.0, 32.0)
SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE = "/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingAvailable"
_DLSS_SETTING_DATA = (
    (
        "enableDlssNeuralRendering",
        "enable",
        False,
        "DLSS 3D-Guided Neural Generation",
        "Enables DLSS 3D-Guided Neural Generation.",
        DlssSettingKind.BOOL,
    ),
    (
        "dlssNeuralRenderingModel",
        "model",
        0,
        "Model",
        "Selects a model variant. 0: Model A, 1: Model B, 2: Model C.",
        DlssSettingKind.ENUM,
        ("Model A", "Model B", "Model C"),
    ),
    (
        "dlssNeuralRenderingIntensity",
        "intensity",
        1.0,
        "Intensity",
        "Overall effect intensity.",
        DlssSettingKind.UNIT_FLOAT,
    ),
    (
        "dlssNeuralRenderingToneIntensity",
        "toneStrength",
        0.3,
        "Tone Intensity",
        "Controls how strongly the model changes local tone.",
        DlssSettingKind.UNIT_FLOAT,
    ),
    (
        "dlssNeuralRenderingStructureIntensity",
        "structuralStrength",
        0.7,
        "Structure Intensity",
        "Controls how strongly the model changes local structure.",
        DlssSettingKind.UNIT_FLOAT,
    ),
    (
        "enableDlssNeuralRenderingAutoMask",
        "useAutoMask",
        False,
        "Enable Auto Mask",
        "Uses Auto Mask instead of the control mask.",
        DlssSettingKind.BOOL,
    ),
    (
        "dlssNeuralRenderingCharacterIntensity",
        "skinStructureStrength",
        0.5,
        "Character Intensity",
        "Structure intensity applied to characters detected by Auto Mask.",
        DlssSettingKind.UNIT_FLOAT,
    ),
    (
        "enableDlssNeuralRenderingHighlightRecovery",
        "enableHighlightRecovery",
        True,
        "Enable Highlight Recovery",
        "Recovers highlights compressed by LDR-domain processing.",
        DlssSettingKind.BOOL,
    ),
    (
        "dlssNeuralRenderingHighlightRecoveryThresholds",
        "highlightRecoveryThresholds",
        (1.0, 8.0, 0.75, 0.99),
        "Highlight Recovery Thresholds",
        "Smoothstep edges: HDR min/max and LDR shoulder min/max.",
        DlssSettingKind.FLOAT4,
    ),
    (
        "enableDlssNeuralRenderingVolumetricImprovement",
        "enableVolumetricControlMask",
        True,
        "Volumetric Improvement",
        "Improves fog and volumetric effects with the control mask.",
        DlssSettingKind.BOOL,
    ),
)
DLSS_SETTINGS = tuple(
    DlssSetting(identifier, f"{_SETTING_PREFIX}/{identifier}", f"{_RUNTIME_PREFIX}.{runtime_name}", *metadata)
    for identifier, runtime_name, *metadata in _DLSS_SETTING_DATA
)
_DLSS_SETTINGS_BY_IDENTIFIER = {setting.identifier: setting for setting in DLSS_SETTINGS}
DLSS_ENABLE = _DLSS_SETTINGS_BY_IDENTIFIER["enableDlssNeuralRendering"]
DLSS_MODEL = _DLSS_SETTINGS_BY_IDENTIFIER["dlssNeuralRenderingModel"]
DLSS_INTENSITY = _DLSS_SETTINGS_BY_IDENTIFIER["dlssNeuralRenderingIntensity"]
DLSS_TONE_INTENSITY = _DLSS_SETTINGS_BY_IDENTIFIER["dlssNeuralRenderingToneIntensity"]
DLSS_STRUCTURE_INTENSITY = _DLSS_SETTINGS_BY_IDENTIFIER["dlssNeuralRenderingStructureIntensity"]
DLSS_AUTO_MASK = _DLSS_SETTINGS_BY_IDENTIFIER["enableDlssNeuralRenderingAutoMask"]
DLSS_CHARACTER_INTENSITY = _DLSS_SETTINGS_BY_IDENTIFIER["dlssNeuralRenderingCharacterIntensity"]
DLSS_HIGHLIGHT_RECOVERY = _DLSS_SETTINGS_BY_IDENTIFIER["enableDlssNeuralRenderingHighlightRecovery"]
DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS = _DLSS_SETTINGS_BY_IDENTIFIER["dlssNeuralRenderingHighlightRecoveryThresholds"]
DLSS_VOLUMETRIC_IMPROVEMENT = _DLSS_SETTINGS_BY_IDENTIFIER["enableDlssNeuralRenderingVolumetricImprovement"]

# Overall intensity remains synchronized for capture compatibility but is not a marketing-facing control.
DLSS_MAIN_SETTINGS = (
    DLSS_ENABLE,
    DLSS_MODEL,
    DLSS_STRUCTURE_INTENSITY,
    DLSS_TONE_INTENSITY,
    DLSS_AUTO_MASK,
    DLSS_CHARACTER_INTENSITY,
)
DLSS_ADVANCED_SETTINGS = (
    DLSS_HIGHLIGHT_RECOVERY,
    DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS,
    DLSS_VOLUMETRIC_IMPROVEMENT,
)


def _coerce_float(value: object, default: float, minimum: float, maximum: float) -> float:
    """Clamp a finite float value or return its default."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return min(max(result, minimum), maximum)


def _coerce_float4(value: object, default: tuple[float, float, float, float]) -> list[float]:
    """Coerce a four-component value into the supported runtime range."""
    if value is None:
        return list(default)
    if isinstance(value, str):
        values = value.replace(",", " ").split()
    elif all(hasattr(value, component) for component in ("x", "y", "z", "w")):
        values = [value.x, value.y, value.z, value.w]
    else:
        try:
            values = list(value)
        except TypeError:
            return list(default)
    if len(values) != 4:
        return list(default)
    return [_coerce_float(component, default[index], *DLSS_FLOAT4_RANGE) for index, component in enumerate(values)]


def coerce_dlss_value(setting: DlssSetting, value: object) -> _DlssValue:
    """Coerce a raw carb setting value according to its DLSS descriptor."""
    if setting.kind == DlssSettingKind.BOOL:
        if value is None:
            return bool(setting.default)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            return bool(setting.default)
        return bool(value)
    if setting.kind == DlssSettingKind.ENUM:
        try:
            selected = int(value)
        except (TypeError, ValueError):
            return int(setting.default)
        if 0 <= selected < len(setting.options):
            return selected
        return int(setting.default)
    if setting.kind == DlssSettingKind.UNIT_FLOAT:
        return _coerce_float(value, float(setting.default), *DLSS_UNIT_FLOAT_RANGE)
    return _coerce_float4(value, setting.default)  # type: ignore[arg-type]


def format_dlss_value(value: _DlssValue) -> str:
    """Format a coerced DLSS value for dxvk-remix config parsing."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return ", ".join(str(component) for component in value)
    return str(value)
