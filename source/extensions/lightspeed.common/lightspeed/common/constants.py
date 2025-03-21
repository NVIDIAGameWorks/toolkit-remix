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

import re
from enum import Enum, IntEnum
from pathlib import Path

from omni import ui
from pxr import Sdf

from .texture_info import CompressionFormat, TextureInfo

WINDOW_NAME = "Trex Main Window"

MATERIAL_RELATIONSHIP = "material:binding"
MATERIAL_INPUTS_DIFFUSE_TEXTURE = "inputs:diffuse_texture"
MATERIAL_INPUTS_NORMALMAP_TEXTURE = "inputs:normalmap_texture"
MATERIAL_INPUTS_NORMALMAP_ENCODING = "inputs:encoding"
MATERIAL_INPUTS_TANGENT_TEXTURE = "inputs:tangent_texture"
MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE = "inputs:reflectionroughness_texture"
MATERIAL_INPUTS_EMISSIVE_MASK_TEXTURE = "inputs:emissive_mask_texture"
MATERIAL_INPUTS_METALLIC_TEXTURE = "inputs:metallic_texture"
MATERIAL_INPUTS_TRANSMITTANCE_TEXTURE = "inputs:transmittance_texture"

PRESERVE_ORIGINAL_ATTRIBUTE = "preserveOriginalDrawCall"

CAPTURED_MAT_PATH_PREFIX = "/Looks/"
CAPTURED_MESH_PATH_PREFIX = "/"
CAPTURED_LIGHT_PATH_PREFIX = "/"

ROOTNODE = "/RootNode"
ROOTNODE_LOOKS = ROOTNODE + "/Looks"
ROOTNODE_INSTANCES = ROOTNODE + "/instances"
ROOTNODE_MESHES = ROOTNODE + "/meshes"
ROOTNODE_LIGHTS = ROOTNODE + "/lights"
ROOTNODE_CAMERA = ROOTNODE + "/Camera"

LIGHT_NAME_PREFIX = "light_"
LIGHT_PATH = ROOTNODE_LIGHTS + "/" + LIGHT_NAME_PREFIX
INSTANCE_NAME_PREFIX = "inst_"
INSTANCE_PATH = ROOTNODE_INSTANCES + "/" + INSTANCE_NAME_PREFIX
MESH_NAME_PREFIX = "mesh_"
MESH_SUB_MESH_NAME = "mesh"
MESH_PATH = ROOTNODE_MESHES + "/" + MESH_NAME_PREFIX
MATERIAL_NAME_PREFIX = "mat_"

SHADER = "Shader"
MATERIAL = "Material"
SCOPE = "Scope"
AUTO = "auto"
RAW = "raw"
SRGB = "sRGB"

LSS_FOLDER = "lss"
LSS_NICKNAME = "nickname"

GAME_READY_ASSETS_FOLDER = "gameReadyAssets"
GAME_READY_REPLACEMENTS_FILE = "replacements.usda"
FLAT_GAME_READY_REPLACEMENTS_FILE = "replacements.usd"

REMIX_ENV_INTERNAL = "RTX_REMIX_INTERNAL"
REMIX_ASSETS_FOLDER = "assets"
REMIX_MODELS_ASSETS_FOLDER = str(Path(REMIX_ASSETS_FOLDER) / "models")
REMIX_TEXTURES_ASSETS_FOLDER = str(Path(REMIX_ASSETS_FOLDER) / "textures")
REMIX_INGESTED_ASSETS_FOLDER = str(Path(REMIX_ASSETS_FOLDER) / "ingested")
REMIX_FOLDER = "rtx-remix"
REMIX_CAPTURE_FOLDER = "captures"
REMIX_MODS_FOLDER = "mods"
REMIX_MOD_FILE = "mod.usda"
REMIX_CAPTURE_BAKER_SUFFIX = "capture_baker"
REMIX_DEPENDENCIES_FOLDER = "deps"
REMIX_SUBUSD_RELATIVE_PATH = "./SubUSDs/"
REMIX_PACKAGE_FOLDER = "package"

CAPTURE_FOLDER = "capture"
MATERIALS_FOLDER = "materials"
MESHES_FOLDER = "meshes"
TEXTURES_FOLDER = "textures"
LIGHTS_FOLDER = "lights"

MESHES_FILE_PREFIX = "mesh_"
LIGHT_FILE_PREFIX = "light_"
MATERIAL_FILE_PREFIX = "mat_"
CAPTURE_FILE_PREFIX = "capture_"

IS_REMIX_REF_ATTR = "IsRemixRef"

SHADER_NAME_OPAQUE = "AperturePBR_Opacity.mdl"
SHADER_NAME_TRANSLUCENT = "AperturePBR_Translucent.mdl"

REMIX_SAMPLE_PATH = "${kit}/../deps/remix_runtime/sample"
REMIX_LAUNCHER_PATH = "${kit}/../deps/remix_runtime/runtime/NvRemixLauncher32.exe"
NVTT_PATH = "${kit}/../deps/tools/nvtt/nvtt_export.exe"
PIX2PIX_ROOT_PATH = str(Path(__file__).parent.joinpath("tools", "pytorch-CycleGAN-and-pix2pix"))
REAL_ESRGAN_ROOT_PATH = str(Path(__file__).parent.joinpath("tools", "realesrgan-ncnn-vulkan-20210901-windows"))
MAT_SR_ROOT_PATH = str(Path(__file__).parent.joinpath("tools", "mat-sr"))
MAT_SR_ARTIFACTS_ROOT_PATH = str(Path(__file__).parent.joinpath("tools", "mat-sr-artifacts"))
PIX2PIX_TEST_SCRIPT_PATH = str(Path(PIX2PIX_ROOT_PATH).joinpath("test.py"))
PIX2PIX_CHECKPOINTS_PATH = str(Path(PIX2PIX_ROOT_PATH).joinpath("checkpoints"))
PIX2PIX_RESULTS_PATH = str(Path(PIX2PIX_ROOT_PATH).joinpath("results"))

REGEX_IN_INSTANCE_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*\/([a-zA-Z0-9_\/]+)*$"  # noqa PLW1401
)
REGEX_IN_MESH_PATH = f"^(.*)({MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*\/([a-zA-Z0-9_\/]+)*$"  # noqa PLW1401
REGEX_MESH_PATH = f"^(.*)({MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_INSTANCE_PATH = f"^(.*)({INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_HASH = f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX}|{MATERIAL_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*(.*)$"  # noqa E501
REGEX_HASH_GENERIC = f"^(.*)([A-Z0-9]{{16}})(_[a-zA-Z0-9]+)*(.*)$"  # noqa PLW1309
REGEX_MESH_TO_INSTANCE_SUB = (
    f"^((.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*)"  # noqa E501
)
REGEX_INSTANCE_TO_MESH_SUB = f"({LIGHT_PATH}|{INSTANCE_PATH}|{MESH_PATH})([A-Z0-9]{{16}})(_[0-9]+)"  # noqa E501
REGEX_LIGHT_PATH = f"^(.*)({LIGHT_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_MESH_INST_LIGHT_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
)
REGEX_SUB_LIGHT_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*\/([a-zA-Z0-9_\/]+)*$"  # noqa
)
REGEX_MAT_MESH_LIGHT_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{MESH_NAME_PREFIX}|{MATERIAL_NAME_PREFIX})([A-Z0-9]{{16}})$"  # noqa E501
)
REGEX_RESERVED_FILENAME = rf"(\b{REMIX_MOD_FILE}\b)|(\b{CAPTURE_FILE_PREFIX}[a-zA-Z]*\b)|(\bmod_{REMIX_CAPTURE_BAKER_SUFFIX}\b)|(\bsublayer\b)"  # noqa E501

# Based on: https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#file-and-directory-names
REGEX_VALID_PATH = r'(?!^.*[\\/]*(?:CON|PRN|AUX|NUL|COM\d|LPT\d)(?:\.[\w\d]+)*$)^((?:\w:)?[^\0-\31"&*:<>?|]+[^\0-\31"&*\.:<>?|])$'  # noqa E501

# REGEX
COMPILED_REGEX_HASH = re.compile(REGEX_HASH)
COMPILED_REGEX_HASH_GENERIC = re.compile(REGEX_HASH_GENERIC)
COMPILED_REGEX_INSTANCE_TO_MESH_SUB = re.compile(REGEX_INSTANCE_TO_MESH_SUB)
COMPILED_REGEX_MESH_TO_INSTANCE_SUB = re.compile(REGEX_MESH_TO_INSTANCE_SUB)

BAD_EXPORT_LOG_PREFIX = "Export is not release ready: "
EXPORT_STATUS_NAME = "remix_replacement_status"
EXPORT_STATUS_RELEASE_READY = "Release Ready"
EXPORT_STATUS_INCOMPLETE_EXPORT = "Export did not finish"
EXPORT_STATUS_PRECHECK_ERRORS = "Precheck Failed"
EXPORT_STATUS_PRECHECK_MEMORY_ERRORS = "Precheck Memory Failed"
EXPORT_STATUS_POSTPROCESS_ERRORS = "PostProcess Errors"


# Texture information describing various aspects of a class of textures such as its encoding and desired export
# format.
TEXTURE_INFO = {
    MATERIAL_INPUTS_DIFFUSE_TEXTURE: TextureInfo(CompressionFormat.BC7, True),
    MATERIAL_INPUTS_NORMALMAP_TEXTURE: TextureInfo(CompressionFormat.BC5, False),
    MATERIAL_INPUTS_TANGENT_TEXTURE: TextureInfo(CompressionFormat.BC5, False),
    MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE: TextureInfo(CompressionFormat.BC4, False),
    MATERIAL_INPUTS_EMISSIVE_MASK_TEXTURE: TextureInfo(CompressionFormat.BC7, True),
    MATERIAL_INPUTS_METALLIC_TEXTURE: TextureInfo(CompressionFormat.BC4, False),
    MATERIAL_INPUTS_TRANSMITTANCE_TEXTURE: TextureInfo(CompressionFormat.BC7, True),
}

AUTOUPSCALE_LAYER_FILENAME = "autoupscale.usda"

USD_EXTENSIONS = [".usd", ".usda", ".usdc"]
SAVE_USD_FILE_EXTENSIONS_OPTIONS = [
    ("*.usda", "Human-readable USD File"),
    ("*.usd", "Binary or Ascii USD File"),
    ("*.usdc", "Binary USD File"),
]
READ_USD_FILE_EXTENSIONS_OPTIONS = [("*.usd, *.usda, *.usdc", "USD Files"), *SAVE_USD_FILE_EXTENSIONS_OPTIONS]

MODEL_INGESTION_SCHEMA_PATH = "${kit}/../exts/lightspeed.trex.app.resources/data/validation_schema/model_ingestion.json"
MATERIAL_INGESTION_SCHEMA_PATH = (
    "${kit}/../exts/lightspeed.trex.app.resources/data/validation_schema/material_ingestion.json"
)
TEXTURE_SCHEMA_PATH = "${kit}/../exts/lightspeed.trex.app.resources/data/validation_schema/ai_texture.json"

INGESTION_SCHEMAS = [
    {"path": MODEL_INGESTION_SCHEMA_PATH, "name": "Model"},
    {"path": MATERIAL_INGESTION_SCHEMA_PATH, "name": "Material"},
]
TEXTURE_SCHEMAS = [
    {"path": TEXTURE_SCHEMA_PATH, "name": "Texture"},
]

ASSET_NEED_INGEST_MESSAGE = (
    "The selected asset is invalid for one of the following reasons:\n"
    "- It was never ingested\n"
    "- It was modified since it was last ingested\n\n"
    "Assets must be ingested for effective use in Remix."
)
ASSET_NEED_INGEST_WINDOW_TITLE = "##Ingestion"
ASSET_NEED_INGEST_WINDOW_OK_LABEL = "Ignore and Import"
ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL = "Ingest Asset"

ASSET_OUTSIDE_OF_PROJ_DIR_MESSAGE = (
    "The selected asset is not located within the project."
    "\n\nAssets must be located within the project folder for referencing to work."
    '\n\nWould you like to copy the asset into the project "assets/ingested/" folder?'
)
ASSET_OUTSIDE_OF_PROJ_DIR_TITLE = "##Outside of Project Directory"
ASSET_OUTSIDE_OF_PROJ_DIR_OK_LABEL = "Copy Asset"

ASSET_OUTSIDE_OF_PROJ_DIR_AND_NEED_INGEST_MESSAGE = (
    "The selected asset is not located within the project and is not ingested."
    "\n\nPlease ingest the asset into the project folder."
)
ASSET_OUTSIDE_OF_PROJ_DIR_AND_NEED_INGEST_TITLE = "##Outside of Project Directory and Not Ingested"

FOCUS_IN_VIEWPORT_TOOLTIP_ENABLED = "Frame prim in the viewport (F)"
FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED = "Prim cannot be framed within the viewport"

MATERIAL_OVERRIDE_PATH = "{prim_node}/Looks"

CREDITS = """
        Project Director
            Jaakko Haapasalo
        Engineering Director
            Alex Dunn
        Product Manager
            Nyle Usmani
        Producer
            Wendy Gram
        Dev Ops
            Zachary Kupu - Lead
        QA
            Dmitriy Marshak - Lead
            Sunny Thakkar
            Lindsay Lutz
            David Driver-Gromm
            David Vega
        Rendering
            Nuno Subtil - Lead
            Mark Henderson
            Peter Kristof
            Riley Alston
            Sultim Tsyrendashiev
            Xiangshun Bei
            Yaobin Ouyang
        Systems
            Sascha Sertel - Lead
            Alexander Jaus
            Lakshmi Vengesanam
            Nicholas Freybler
        Tools
            Damien Bataille - Lead
            Shona Gillard
            Nicolas Kendall-Bar
            Ed Leafe
            Pierre-Olivier Trottier
            Sam Bourne
            Scott Fitzpatrick
            Sam Ahiro
        AI Research
            James Lucas
        Art Lead
            Vern Andres-Quentin
        """

LICENSE_AGREEMENT_URL = (
    "https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html"
)
DOCUMENTATION_URL = "https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/latest/"
DOCUMENTATION_ROOT_URL = f"{DOCUMENTATION_URL}docs/"
QUICK_START_GUIDE_URL = f"{DOCUMENTATION_ROOT_URL}gettingstarted/learning-runtimesetup.html"
RELEASE_NOTES_URL = f"{DOCUMENTATION_ROOT_URL}remix-releasenotes.html"

TUTORIALS_URL = "https://www.youtube.com/playlist?list=PL4w6jm6S2lzvgJ97T1_VbLGBR_l6zzOUm"
COMMUNITY_SUPPORT_URL = (
    "https://github.com/NVIDIAGameWorks/rtx-remix/?tab=readme-ov-file#forums-support--community-resources"
)
GITHUB_URL = "https://github.com/NVIDIAGameWorks/rtx-remix/"
REPORT_ISSUE_URL = "https://github.com/NVIDIAGameWorks/rtx-remix/issues"

REMIX_CATEGORIES = {
    "World UI": {
        "attr": "remix_category:world_ui",
        "tooltip": "Textures on draw calls that should be treated as screen space UI elements.",
        "full_description": [
            "Textures on draw calls that should be treated as",
            "screen space UI elements. All exclusively UI-related",
            "textures should be classified this way and doing so",
            "allows the UI to be rasterized on top of the ray traced",
            "scene like usual. Note that currently the first UI texture",
            "encountered triggers RTX injection (though this may change",
            "in the future as this does cause issues with games that",
            "draw UI mid-frame).",
        ],
    },
    "World Matte": {
        "attr": "remix_category:world_matte",
        "tooltip": "Textures on draw calls that should be treated as world space UI elements.",
        "full_description": [
            "Textures on draw calls that should be treated as",
            "world space UI elements. Unlike typical UI textures",
            "this option is useful for improved rendering of UI",
            "elements which appear as part of the scene (moving",
            "around in 3D space rather than as a screen space element).",
        ],
    },
    "Sky": {
        "attr": "remix_category:sky",
        "tooltip": "Geometries from draw calls used for the sky or are otherwise intended to be very far away from the camera at all times (no parallax).",  # noqa E501
        "full_description": [
            "Geometries from draw calls used for the sky or",
            "are otherwise intended to be very far away from",
            "the camera at all times (no parallax). Any draw",
            "calls using a geometry hash in this list will be",
            "treated as sky and rendered as such in a manner",
            "different from typical geometry. The geometry hash",
            "being used for sky detection is based off of the asset",
            "hash rule.",
        ],
    },
    "Ignore": {
        "attr": "remix_category:ignore",
        "tooltip": "Textures on draw calls that should be ignored.",
        "full_description": [
            "Textures on draw calls that should be ignored. Any draw",
            "call using an ignore texture will be skipped and not ray",
            "traced, useful for removing undesirable rasterized effects",
            "or geometry not suitable for ray tracing.",
        ],
    },
    "Ignore Lights": {
        "attr": "remix_category:ignore_lights",
        "tooltip": "Lights that should be ignored.",
        "full_description": [
            "Lights that should be ignored. Any matching light will",
            "be skipped and not added to be ray traced.",
        ],
    },
    "Ignore Anti-culling": {
        "attr": "remix_category:ignore_anti_culling",
        "tooltip": "Textures that are forced to extend life length when anti-culling is enabled.",
        "full_description": [
            "Textures that are forced to extend life length when",
            "anti-culling is enabled. Some games use different culling",
            "methods we can't fully match, use this option to manually",
            "add textures to force extend their life when anti-culling fails.",
        ],
    },
    "Ignore Motion Blur": {
        "attr": "remix_category:ignore_motion_blur",
        "tooltip": "Disable motion blur for meshes with specific texture.",
        "full_description": ["Disable motion blur for meshes with specific texture."],
    },
    "Ignore Opacity Micromap": {
        "attr": "remix_category:ignore_opacity_micromap",
        "tooltip": "Textures to ignore when generating Opacity Micromaps.",
        "full_description": [
            "Textures to ignore when generating Opacity Micromaps.",
            "This generally does not have to be set and is only useful",
            "for black listing problematic cases for Opacity Micromap",
            "usage.",
        ],
    },
    "Hidden": {
        "attr": "remix_category:hidden",
        "tooltip": "Textures on draw calls that should be hidden from rendering.",
        "full_description": [
            "Textures on draw calls that should be hidden from rendering,",
            "but not totally ignored. This is similar to rtx.ignoreTextures",
            "but instead of completely ignoring such draw calls they are",
            "only hidden from rendering, allowing for the hidden objects to",
            "still appear in captures. As such, this is mostly only a",
            "development tool to hide objects during development until",
            "they are properly replaced, otherwise the objects should be",
            "ignored with rtx.ignoreTextures instead for better",
            "performance.",
        ],
    },
    "Particle": {
        "attr": "remix_category:particle",
        "tooltip": "Textures on draw calls that should be treated as particles.",
        "full_description": [
            "Textures on draw calls that should be treated",
            "as particles. When objects are marked as particles",
            "more approximate rendering methods are leveraged,",
            "allowing for more efficient and typically better",
            "looking particle rendering. Generally any",
            "billboard-like blended particle objects in the original",
            "application should be classified this way.",
        ],
    },
    "Beam": {
        "attr": "remix_category:beam",
        "tooltip": "Textures on draw calls that are already particles or emissively blended and have beam-like geometry.",  # noqa E501
        "full_description": [
            "Textures on draw calls that are already particles or",
            "emissively blended and have beam-like geometry.",
            "To handle cases where a regular billboard may not apply, a",
            "different beam mode is used to treat objects as more of",
            "a cylindrical beam and re-orient around its main spanning axis,",
            "allowing for better rendering of these beam-like effect objects.",
        ],
    },
    "Decal": {
        "attr": "remix_category:decal_Static",
        "tooltip": "Textures on draw calls used for static geometric decals or decals with complex topology.",
        "full_description": [
            "Textures on draw calls used for static geometric",
            "decals or decals with complex topology. These materials",
            "will be blended over the materials underneath them when",
            "decal material blending is enabled. A small configurable",
            "offset is applied to each flat/co-planar part of these decals",
            "to prevent coplanar geometric cases (which poses problems",
            "for ray tracing).",
        ],
    },
    "Alpha Blend to Cutout": {
        "attr": "remix_category:alpha_blend_to_cutout",
        "tooltip": "When an object is added to the cutout textures list it will have a cutout alpha mode forced on it.",
        "full_description": [
            "When an object is added to the cutout textures list it",
            "will have a cutout alpha mode forced on it, using this",
            "value for the alpha test. This is meant to improve the",
            "look of some legacy mode materials using low-resolution",
            "textures and alpha blending in Remix. Such objects are",
            "generally better handled with actual replacement assets",
            "using fully opaque geometry replacements or alpha cutout",
            "with higher resolution textures, so this should only be",
            "relied on until proper replacements can be authored.",
        ],
    },
    "Terrain": {
        "attr": "remix_category:terrain",
        "tooltip": "Albedo textures that are baked blended together to form a unified terrain texture used during ray tracing.",  # noqa E501
        "full_description": [
            "Albedo textures that are baked blended together to form",
            "a unified terrain texture used during ray tracing. Put",
            "albedo textures into this category if the game renders",
            "terrain as a blend of multiple textures.",
        ],
    },
    "Animated Water": {
        "attr": "remix_category:animated_water",
        "tooltip": 'Textures on draw calls to be treated as "animated water".',
        "full_description": [
            'Textures on draw calls to be treated as "animated water".',
            "Objects with this flag applied will animate their normals",
            "to fake a basic water effect based on the layered water",
            "material parameters, and only when",
            "rtx.opaqueMaterial.layeredWaterNormalEnable is set to true.",
            "Should typically be used on static water planes that the",
            "original application may have relied on shaders to animate",
            "water on.",
        ],
    },
    "Third Person Player Model": {
        "attr": "remix_category:third_person_player_model",
        "tooltip": "Treated as a third person model to be used for shadows, but not rendered.",
        "full_description": ["Treated as a third person model to be used for", "shadows, but not rendered."],
    },
    "Third Person Player Body": {
        "attr": "remix_category:third_person_player_body",
        "tooltip": "Treated as a third person model to be used for shadows, but not rendered.",
        "full_description": ["Treated as a third person model to be used for", "shadows, but not rendered."],
    },
    "Ignore Baked Lighting": {
        "attr": "remix_category:ignore_baked_lighting",
        "tooltip": "Textures for which to ignore two types of baked lighting, Texture Factors and Vertex Color.",
        "full_description": [
            "Textures for which to ignore two types of baked",
            "lighting. Texture Factors and Vertex Color. Texture",
            "Factor disablement: Using this feature on selected",
            "textures will eliminate the texture factors.",
            "Vertex Color disablement: Using this feature on selected",
            "textures will eliminate the vertex colors. Note, enabling",
            "this setting will automatically disable multiple-stage",
            "texture factor blendings for the selected textures.",
        ],
    },
}

REMIX_CATEGORIES_DISPLAY_NAMES = {v["attr"]: k for k, v in REMIX_CATEGORIES.items()}
HIDDEN_REMIX_CATEGORIES = ["Third Person Player Body", "Third Person Player Model", "Hidden", "Ignore", "Ignore Lights"]

REMIX_OPTIONAL_LIGHT_ATTRIBUTES = [
    {
        "token": "inputs:volumetric_radiance_scale",
        "name": "Volumetric Radiance Scale",
        "type": Sdf.ValueTypeNames.Float,
        "default_value": 1.0,
        "documentation": "Multiplies how bright this light seems to volumetric mediums like fog or suspended dust.\n"
        + "This can be used to enhance the god-rays coming from this light.\n"
        + "Not physically accurate.",
    },
]

PROPERTIES_NAMES_COLUMN_WIDTH = ui.Pixel(270)


# This should match the `normalmap_encoding` in AperturePBR_normal.mdl
class NormalMapEncodings(IntEnum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2


class GlobalEventNames(Enum):
    IMPORT_CAPTURE_LAYER = "Import capture layer"
    ACTIVE_VIEWPORT_CHANGED = "Active viewport changed"  # Emitted by trex.viewports.shared.widgets
    CONTEXT_CHANGED = "Context changed"
    PAGE_CHANGED = "Page changed"
