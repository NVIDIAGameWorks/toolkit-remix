from enum import IntEnum
from pathlib import Path

MATERIAL_INPUTS_DIFFUSE_TEXTURE = "inputs:diffuse_texture"
MATERIAL_INPUTS_NORMALMAP_TEXTURE = "inputs:normalmap_texture"
MATERIAL_INPUTS_NORMALMAP_ENCODING = "inputs:encoding"
MATERIAL_INPUTS_TANGENT_TEXTURE = "inputs:tangent_texture"
MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE = "inputs:reflectionroughness_texture"
MATERIAL_INPUTS_EMISSIVE_MASK_TEXTURE = "inputs:emissive_mask_texture"
MATERIAL_INPUTS_METALLIC_TEXTURE = "inputs:metallic_texture"
MATERIAL_INPUTS_TRANSMITTANCE_TEXTURE = "inputs:transmittance_texture"
CAPTURED_MAT_PATH_PREFIX = "/Looks/"
CAPTURED_MESH_PATH_PREFIX = "/"
CAPTURED_LIGHT_PATH_PREFIX = "/"
ROOTNODE = "/RootNode"
ROOTNODE_LOOKS = ROOTNODE + "/Looks"
ROOTNODE_INSTANCES = ROOTNODE + "/instances"
ROOTNODE_MESHES = ROOTNODE + "/meshes"
ROOTNODE_LIGHTS = ROOTNODE + "/lights"
INSTANCE_PATH = ROOTNODE_INSTANCES + "/inst_"
MESH_PATH = ROOTNODE_MESHES + "/mesh_"
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

BAD_EXPORT_LOG_PREFIX = "Export is not release ready: "
EXPORT_STATUS_NAME = "remix_replacement_status"
EXPORT_STATUS_RELEASE_READY = "Release Ready"
EXPORT_STATUS_PRECHECK_ERRORS = "Precheck Failed"
EXPORT_STATUS_POSTPROCESS_ERRORS = "PostProcess Errors"

TEXTURE_COMPRESSION_LEVELS = {
    MATERIAL_INPUTS_DIFFUSE_TEXTURE: "bc7",
    MATERIAL_INPUTS_NORMALMAP_TEXTURE: "bc5",
    MATERIAL_INPUTS_TANGENT_TEXTURE: "bc5",
    MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE: "bc4",
    MATERIAL_INPUTS_EMISSIVE_MASK_TEXTURE: "bc7",
    MATERIAL_INPUTS_METALLIC_TEXTURE: "bc4",
    MATERIAL_INPUTS_TRANSMITTANCE_TEXTURE: "bc7",
}

AUTOUPSCALE_LAYER_FILENAME = "autoupscale.usda"


# This should match the `normalmap_encoding` in AperturePBR_normal.mdl
class NormalMapEncodings(IntEnum):
    OCTAHEDRAL = 0
    TANGENT_SPACE_OGL = 1
    TANGENT_SPACE_DX = 2
