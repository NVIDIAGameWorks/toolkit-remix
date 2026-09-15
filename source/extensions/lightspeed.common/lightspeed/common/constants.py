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
from enum import Enum, IntEnum, StrEnum
from pathlib import Path

from omni import ui
from pxr import Sdf

from .texture_info import CompressionFormat, MipFilter, TextureInfo

WINDOW_NAME = "Remix Main Window"

MATERIAL_RELATIONSHIP = "material:binding"
MATERIAL_INPUTS_DIFFUSE_TEXTURE = "inputs:diffuse_texture"
MATERIAL_INPUTS_NORMALMAP_TEXTURE = "inputs:normalmap_texture"
MATERIAL_INPUTS_NORMALMAP_ENCODING = "inputs:encoding"
MATERIAL_INPUTS_TANGENT_TEXTURE = "inputs:tangent_texture"
MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE = "inputs:reflectionroughness_texture"
MATERIAL_INPUTS_EMISSIVE_MASK_TEXTURE = "inputs:emissive_mask_texture"
MATERIAL_INPUTS_METALLIC_TEXTURE = "inputs:metallic_texture"
MATERIAL_INPUTS_TRANSMITTANCE_TEXTURE = "inputs:transmittance_texture"
MATERIAL_INPUTS_HEIGHT_TEXTURE = "inputs:height_texture"

PRESERVE_ORIGINAL_ATTRIBUTE = "preserveOriginalDrawCall"

CAPTURED_MAT_PATH_PREFIX = "/Looks/"
CAPTURED_MESH_PATH_PREFIX = "/"
CAPTURED_LIGHT_PATH_PREFIX = "/"

ROOTNODE = "/RootNode"
ROOTNODE_LOOKS = ROOTNODE + "/Looks"
ROOTNODE_INSTANCES = ROOTNODE + "/instances"
ROOTNODE_MESHES = ROOTNODE + "/meshes"
ROOTNODE_LIGHTS = ROOTNODE + "/lights"
ROOTNODE_CAMERA = ROOTNODE + "/Camera"  # legacy capture camera location
CAPTURED_CAMERA = ROOTNODE + "/cameras/Camera"

# Render settings prim a capture stores the rtx.* options it was taken with on.
CAPTURED_REMIX_SETTINGS = "/remix_settings"
CAPTURED_REMIX_CONFIG_ATTR = "remix:remix_config"
# Pre-namespace spelling. Hydra gathers only namespaced attributes off a render settings
# prim, so this one never reaches HdRemix.
CAPTURED_REMIX_CONFIG_LEGACY_ATTR = "remix_config"

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

REMIX_SAMPLE_PATH = "${lightspeed.trex.app.resources}/deps/remix_runtime/sample"
REMIX_LAUNCHER_PATH = "${lightspeed.trex.app.resources}/deps/remix_runtime/runtime/NvRemixLauncher32.exe"

# REGEX Constants

# Prim Path REGEX
REGEX_IN_INSTANCE_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*/([a-zA-Z0-9_/]+)*$"
)
REGEX_MESH_PATH_BASE = rf"^(.*)({MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*"
REGEX_MESH_PATH = rf"{REGEX_MESH_PATH_BASE}$"
# direct children of mesh group
REGEX_IN_MESH_PATH = rf"{REGEX_MESH_PATH_BASE}/([a-zA-Z0-9_/]+)*$"
# all children of mesh group
REGEX_IN_MESH_CHILDREN_PATH = rf"{REGEX_MESH_PATH_BASE}/*([a-zA-Z0-9_/]+)*$"
REGEX_MESH_PATH_AND_CHILDREN = rf"{REGEX_MESH_PATH_BASE}(/*[a-zA-Z0-9_/]*)*$"
REGEX_INSTANCE_PATH = f"^(.*)({INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_MESH_TO_INSTANCE_SUB = (
    f"^((.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*)"
)
REGEX_INSTANCE_TO_MESH_SUB = f"({LIGHT_PATH}|{INSTANCE_PATH}|{MESH_PATH})([A-Z0-9]{{16}})(_[0-9]+)"
REGEX_LIGHT_PATH_BASE = f"^(.*)({LIGHT_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*"
REGEX_LIGHT_PATH = rf"{REGEX_LIGHT_PATH_BASE}$"
# direct children of light group
REGEX_IN_LIGHT_PATH = rf"{REGEX_LIGHT_PATH_BASE}/([a-zA-Z0-9_/]+)*$"
# all children of light group
REGEX_IN_LIGHT_CHILDREN_PATH = rf"{REGEX_LIGHT_PATH_BASE}/*([a-zA-Z0-9_/]+)*$"
REGEX_LIGHT_PATH_AND_CHILDREN = rf"{REGEX_LIGHT_PATH_BASE}(/*[a-zA-Z0-9_/]*)*$"
# fmt: off
REGEX_MESH_INST_LIGHT_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
)
REGEX_SUB_LIGHT_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*/([a-zA-Z0-9_/]+)*$"
)
REGEX_MAT_MESH_LIGHT_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{MESH_NAME_PREFIX}|{MATERIAL_NAME_PREFIX})([A-Z0-9]{{16}})$"
)
# fmt: on

# Hash REGEX
REGEX_HASH = f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX}|{MATERIAL_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*(.*)$"
REGEX_HASH_GENERIC = r"^(.*)([A-Z0-9]{16})(_[a-zA-Z0-9]+)*(.*)$"

# Filename and Filepath REGEX
REGEX_RESERVED_FILENAME = rf"(\b{REMIX_MOD_FILE}\b)|(\b{CAPTURE_FILE_PREFIX}[a-zA-Z]*\b)|(\bmod_{REMIX_CAPTURE_BAKER_SUFFIX}\b)|(\bsublayer\b)"
# Based on: https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#file-and-directory-names
REGEX_VALID_PATH = (
    r'(?!^.*[\/]*(?:CON|PRN|AUX|NUL|COM\d|LPT\d)(?:\.[\w\d]+)*$)^((?:\w:)?[^\0-\31"&*:<>?|]+[^\0-\31"&*\.:<>?|])$'
)

# Compiled REGEX
COMPILED_REGEX_HASH = re.compile(REGEX_HASH)
COMPILED_REGEX_HASH_GENERIC = re.compile(REGEX_HASH_GENERIC)
COMPILED_REGEX_INSTANCE_TO_MESH_SUB = re.compile(REGEX_INSTANCE_TO_MESH_SUB)
COMPILED_REGEX_MESH_TO_INSTANCE_SUB = re.compile(REGEX_MESH_TO_INSTANCE_SUB)

# Export Constants
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
    MATERIAL_INPUTS_HEIGHT_TEXTURE: TextureInfo(CompressionFormat.BC4, False, mip_filter=MipFilter.MAX),
}

AUTOUPSCALE_LAYER_FILENAME = "autoupscale.usda"

USD_EXTENSIONS = [".usd", ".usda", ".usdc"]
SAVE_USD_FILE_EXTENSIONS_OPTIONS = [
    ("*.usda", "Human-readable USD File"),
    ("*.usd", "Binary or Ascii USD File"),
    ("*.usdc", "Binary USD File"),
]
READ_USD_FILE_EXTENSIONS_OPTIONS = [("*.usd, *.usda, *.usdc", "USD Files"), *SAVE_USD_FILE_EXTENSIONS_OPTIONS]

MODEL_INGESTION_SCHEMA_PATH = "${lightspeed.trex.app.resources}/data/validation_schema/model_ingestion.json"
MATERIAL_INGESTION_SCHEMA_PATH = "${lightspeed.trex.app.resources}/data/validation_schema/material_ingestion.json"

INGESTION_SCHEMAS = [
    {"path": MODEL_INGESTION_SCHEMA_PATH, "name": "Model"},
    {"path": MATERIAL_INGESTION_SCHEMA_PATH, "name": "Material"},
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
FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED = "The prim cannot be framed in the viewport"

MATERIAL_OVERRIDE_PATH = "{prim_node}/Looks"

CREDITS = """
        Project Director
            Jaakko Haapasalo
        Engineering Director
            Alex Dunn
        Product Manager
            Nyle Usmani
            Ike Nnoli
        Producer
            David Driver-Gomm
            Wendy Gram
        Dev Ops
            Zachary Kupu - Lead
            Eugenio Naselli
            Ian Hutchings
            Peter Thacker
        QA
            Dmitriy Marshak - Lead
            David Vega
            Jason Howard
            Jasper Wilson
            Lindsay Lutz
            Sunny Thakkar
            Chris Workman
        Rendering
            Nuno Subtil - Lead
            Jerran Schmidt
            Jeremy Shopf
            Mark Henderson
            Peter Kristof
            Riley Alston
            Sultim Tsyrendashiev
            Xiangshun Bei
            Yaobin Ouyang
            Luis Mendez
            Alexey Panteleev
            Ilya Terentiev
        Systems
            Sascha Sertel - Lead
            Alexander Jaus
            Kamil Sławicki
            Jeremy Ingham
            Lakshmi Vengesanam
            Nicholas Freybler
        Tools
            Nicolas Kendall-Bar - Lead
            Carlos Anguiano
            Damien Bataille
            Ed Leafe
            Emanuel Kozerski
            Pierre-Olivier Trottier
            Sam Ahiro
            Sam Bourne
            Scott Fitzpatrick
            Shona Gillard
        AI Research
            James Lucas
        Art
            Vernon Andres-Quentin - Lead
            Filippo Baraccani
            Kelsey Blanton
            Stan Brown
            Rafael Chies
            Derk Elshof
            Ivan Filipchenko
            Hunter Hazen
            Fred Hooper
            Vadym Kovalenko
            Max Kozhevnikov
            Gabriele Leone
            Evgeny Leonov
            Emmanuel Marshall
            Aleksey Semenov
            Ilya Shelementsev
            Dmytro Siromakha
            Oleksandr Smirnov
            Mostafa Sobhi
            Chase Telegin
            Oleksii Tronchuk
        PR/Marketing
            Tim Adams
            Brian Burke
            Andrew Iain Burnes
            Dave Janssen
            Jessie Lawrence
            Randy Niu
            Mike Pepe
            Mark Religioso
            Kris Rey
            Suroosh Taeb
            Chris Turner
            Keoki Young
            Jakob Zamora
        Special Thanks
            Alex Hyder
            Keith Li
            Jarvis McGee
            Liam Middlebrook
            Adam Moss
            Jason Paul
            Seth Schneider
            Mike Songy
            John Spitzer
            Sylvain Trottier
            --
            Everyone contributing to #ct-lss-classic-rtx
            Valve
        In Memory
            Landon Montgomery
        Github Contributors
            Lorenzo 'King Vulpes' Acevedo IV
            Quinn 'Binq Adams' Baddams
            Samuel 'CR' Bowman
            Alexis 'Sortifal' Bruneteau
            Ethan 'Xenthio' Cardwell
            Alexander 'xoxor4d' Engel
            James Horsley 'mmdanggg2'
            Kim 'Kim2091'
            Leonardo Leotte
            Jeffrey 'skurtyyskirts' Munoz
            Nico Rodrigues-McKenna
            Friedrich 'pixelcluster' Vock
            James 'jdswebb' Webb
            David 'King David' Wiltos
            Dayton 'watbulb'
            Basil 'EliteCombineSoldier'
        """

LICENSE_AGREEMENT_URL = (
    "https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html"
)
DOCUMENTATION_URL = "https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/latest/"
DOCUMENTATION_ROOT_URL = f"{DOCUMENTATION_URL}docs/"
QUICK_START_GUIDE_URL = f"{DOCUMENTATION_ROOT_URL}gettingstarted/learning-toolkitsetup.html"
LOGIC_DOCUMENTATION_URL = f"{DOCUMENTATION_ROOT_URL}howto/learning-logic.html"
RELEASE_NOTES_URL = f"{DOCUMENTATION_ROOT_URL}remix-releasenotes.html"

TUTORIALS_URL = f"{DOCUMENTATION_ROOT_URL}tutorials/tutorial-videos.html"
COMMUNITY_SUPPORT_URL = (
    "https://github.com/NVIDIAGameWorks/rtx-remix/?tab=readme-ov-file#forums-support--community-resources"
)
GITHUB_URL = "https://github.com/NVIDIAGameWorks/rtx-remix/"
REPORT_ISSUE_URL = "https://github.com/NVIDIAGameWorks/rtx-remix/issues"
DXVK_REMIX_GITHUB_URL = "https://github.com/NVIDIAGameWorks/dxvk-remix/"
DXVK_REMIX_DOCUMENTATION_URL = f"{DXVK_REMIX_GITHUB_URL}blob/main/documentation"

# Categories
REMIX_CATEGORIES_ALLOWED_PRIM_TYPES = ["Mesh"]
HIDDEN_REMIX_CATEGORIES = ["Third Person Player Body", "Third Person Player Model", "Hidden", "Ignore", "Ignore Lights"]

REMIX_OPTIONAL_LIGHT_ATTRIBUTES = [
    {
        "token": "inputs:volumetric_radiance_scale",
        "name": "Volumetric Radiance Scale",
        "type": Sdf.ValueTypeNames.Float,
        "default_value": 1.0,
        "documentation": (
            "Multiplies how bright this light seems to volumetric mediums like fog or suspended dust.\n"
            "This can be used to enhance the god-rays coming from this light.\n"
            "Not physically accurate."
        ),
    },
]

PROPERTIES_NAMES_COLUMN_WIDTH = ui.Pixel(270)


# This should match the `normalmap_encoding` in AperturePBR_normal.mdl
class NormalMapEncodings(IntEnum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2


class GlobalEventNames(Enum):
    CAPTURE_LAYER_IMPORTED = "Capture layer imported"
    ACTIVE_VIEWPORT_CHANGED = "Active viewport changed"  # Emitted by trex.viewports.shared.widgets
    VIEWPORT_DELETE_SELECTION_REQUEST = "Viewport delete selection request"
    VIEWPORT_FRAME_PRIMS_REQUEST = "Viewport frame prims request"
    CONTEXT_CHANGED = "Context changed"
    PAGE_CHANGED = "Page changed"
    OPEN_WORKSPACE = "Open the Workspace Page Layout"

    # Requests to load a project by path.
    # Subscribers should return a True/False approving/interrupting the load. I.e: For pending changes.
    LOAD_PROJECT_PATH = "Load Toolkit Project Path"
    IMPORT_LAYER = "Import Layer (LayerType, path, use_existing_file)"

    LOGIC_GRAPH_CREATE_REQUEST = "Logic graph create request"  # Emitted with (parent: Usd.Prim)
    LOGIC_GRAPH_EDIT_REQUEST = "Logic graph edit request"  # Emitted with (graph: Usd.Prim)


# Remix Logic
OMNI_GRAPH_TYPE = "OmniGraph"
OMNI_GRAPH_NODE_TYPE = "OmniGraphNode"
OMNI_GRAPH_NODE_TYPES = ("OmniGraph", "OmniGraphNode")

# Particle System
PARTICLE_SCHEMA_NAME = "ParticleSystemAPI"
PARTICLE_ALLOWED_PRIM_TYPES = ["Mesh", "Material"]
PARTICLE_PRIMVAR_PREFIX = "primvars:particle:"
PARTICLE_HIDE_EMITTER_ATTR = PARTICLE_PRIMVAR_PREFIX + "hideEmitter"

# Viewport
VIEWPORT_MENU_SHOW_BY_TYPE = "Show By Type"

# Modding top bar
UNTITLED_PROJECT_NAME = "Untitled Project"


class WindowNames(StrEnum):
    """Names registered with ``ui.Workspace`` for RTX Remix windows."""

    VIEWPORT = "Viewport"
    STAGE_MANAGER = "Stage Manager"
    PROPERTIES = "Editor"  # TODO: Rename to Properties once we break the component to have only property panes in it.
    SIDEBAR = "Sidebar"
    MOD_PACKAGING = "Packaging"
    HOME_PAGE = "Home Page"
    INGESTCRAFT = "Ingestion"
    PROJECT_SETUP = "Project Setup"
    CAPTURES = "Captures"
    REMIX_LOGIC_GRAPH = "Logic Graph"
    COMFYUI_SETUP = "ComfyUI Setup"
    COMFYUI_WORKFLOW = "ComfyUI Workflow"
    JOB_QUEUE = "Job Queue"
    JOB_DETAILS = "Job Details"


class Layouts(Enum):
    HOME_PAGE = "HomePage"
    WORKSPACE_PAGE = "WorkspacePage"
    INGESTCRAFT = "IngestCraft"


class LayoutFiles(StrEnum):
    """Resource keys for built-in RTX Remix quick-layout files."""

    HOME_PAGE = "home_page_default_layout"
    WORKSPACE_PAGE = "stagecraft_default_layout"
    INGESTCRAFT = "ingestcraft_default_layout"
    TEXTURECRAFT = "texturecraft_default_layout"
    PACKAGING = "packaging_default_layout"
    LOGIC_GRAPH = "logic_default_layout"
