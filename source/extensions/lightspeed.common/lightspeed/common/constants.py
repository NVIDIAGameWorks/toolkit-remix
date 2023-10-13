import re
from enum import Enum, IntEnum
from pathlib import Path

from .texture_info import CompressionFormat, TextureInfo

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
REGEX_MESH_PATH = f"^(.*)({MESH_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_INSTANCE_PATH = f"^(.*)({INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_HASH = f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX}|{MESH_NAME_PREFIX}|{MATERIAL_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*(.*)$"  # noqa E501
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

# Based on: https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#file-and-directory-names
REGEX_VALID_PATH = r'(?!^.*[\\/]*(?:CON|PRN|AUX|NUL|COM\d|LPT\d)(?:\.[\w\d]+)*$)^((?:\w:)?[^\0-\31"&*:<>?|]+[^\0-\31"&*\.:<>?|])$'  # noqa E501

# REGEX
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
INGESTION_SCHEMA_PATHS = [MODEL_INGESTION_SCHEMA_PATH, MATERIAL_INGESTION_SCHEMA_PATH]

ASSET_NEED_INGEST_MESSAGE = (
    "The selected asset was not ingested or modified since it was last ingested.\n\n"
    "Assets are expected to be ingested."
)
ASSET_NEED_INGEST_WINDOW_TITLE = "##Ingestion"
ASSET_NEED_INGEST_WINDOW_OK_LABEL = "Ignore and import the asset"
ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL = "Go to ingest tab"

MATERIAL_OVERRIDE_PATH = "{prim_node}/Looks"


# This should match the `normalmap_encoding` in AperturePBR_normal.mdl
class NormalMapEncodings(IntEnum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2


class GlobalEventNames(Enum):
    IMPORT_CAPTURE_LAYER = "Import capture layer"
