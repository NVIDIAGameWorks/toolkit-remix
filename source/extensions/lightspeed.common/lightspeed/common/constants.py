from enum import IntEnum
from pathlib import Path

from .texture_info import CompressionFormat, TextureInfo

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
LIGHT_NAME_PREFIX = "light_"
LIGHT_PATH = ROOTNODE_LIGHTS + "/" + LIGHT_NAME_PREFIX
INSTANCE_NAME_PREFIX = "inst_"
INSTANCE_PATH = ROOTNODE_INSTANCES + "/" + INSTANCE_NAME_PREFIX
MESH_NAME_PREFIX = "mesh_"
MESH_PATH = ROOTNODE_MESHES + "/" + MESH_NAME_PREFIX
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
CAPTURE_FOLDER = "capture"
MATERIALS_FOLDER = "materials"
MESHES_FOLDER = "meshes"
LIGHTS_FOLDER = "lights"
MESHES_FILE_PREFIX = "mesh_"
LIGHT_FILE_PREFIX = "light_"
MATERIAL_FILE_PREFIX = "mat_"
CAPTURE_FILE_PREFIX = "capture_"
NVTT_PATH = str(Path(__file__).parent.joinpath("tools", "nvtt", "nvtt_export.exe"))
PIX2PIX_ROOT_PATH = str(Path(__file__).parent.joinpath("tools", "pytorch-CycleGAN-and-pix2pix"))
PIX2PIX_TEST_SCRIPT_PATH = str(Path(PIX2PIX_ROOT_PATH).joinpath("test.py"))
PIX2PIX_CHECKPOINTS_PATH = str(Path(PIX2PIX_ROOT_PATH).joinpath("checkpoints"))
PIX2PIX_RESULTS_PATH = str(Path(PIX2PIX_ROOT_PATH).joinpath("results"))

REGEX_INSTANCE_PATH = f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_LIGHT_PATH = f"^(.*)({LIGHT_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*$"
REGEX_SUB_INSTANCE_PATH = (
    f"^(.*)({LIGHT_NAME_PREFIX}|{INSTANCE_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*\/([a-zA-Z0-9_]+)*$"  # noqa
)
REGEX_SUB_LIGHT_PATH = f"^(.*)({LIGHT_NAME_PREFIX})([A-Z0-9]{{16}})(_[0-9]+)*\/([a-zA-Z0-9_\/]+)*$"  # noqa

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


# This should match the `normalmap_encoding` in AperturePBR_normal.mdl
class NormalMapEncodings(IntEnum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2
