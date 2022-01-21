from pathlib import Path
import os
import asyncio
import json
import carb
import carb.tokens
import omni
import omni.kit.commands
import omni.usd
import omni.client
import omni.ui as ui
from omni.kit.window.toolbar.widget_group import WidgetGroup
from lightspeed.common import constants
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType
from pxr import Sdf, Tf, Usd, UsdShade, UsdGeom

# COPIED FROM https://gitlab-master.nvidia.com/dbataille/kit_extensions/-/blob/master/omni.kit.mapper/omni/kit/mapper/python/core/material_utils.py#L87
def remove_attr_session_override(prim: Usd.Prim, keep_value_on_attrs: list = None):
    """Remove attributes that are overridden from the root layer from the shader"""
    stage = omni.usd.get_context().get_stage()
    root_layer = stage.GetRootLayer()
    for attr in prim.GetAuthoredAttributes():
        if keep_value_on_attrs:
            if attr.GetName() in keep_value_on_attrs:
                continue
        if root_layer.GetAttributeAtPath(attr.GetPath()):
            attr_spec = root_layer.GetAttributeAtPath(attr.GetPath())
            shade_input = UsdShade.Input(attr)
            if shade_input:
                attr_spec.connectionPathList.ClearEdits()
                prim_spec = root_layer.GetPrimAtPath(prim.GetPath())
                del prim_spec.properties[attr_spec.name]

def load_mdl_parameters_for_prim(prims: Usd.Prim, call_back: callable = None):
    """
    Load MDL attributes

    Args:
        prims: shader to load MDL attributes from
        call_back: callback to execute when the MDL is loaded
    """

    async def async_load_mdl():
        for prim in prims:
            # TODO: wait for a sync version of this
            await omni.usd.get_context().load_mdl_parameters_for_prim_async(
                prim
            )
        if call_back is not None:
            call_back()
    asyncio.ensure_future(async_load_mdl())

def replace_shader(prim: Usd.Prim, mdl_path: str, keep_value_on_attrs: list = None, keep_all_value: bool = False):
    """Replace a MDL path of a shader prim"""
    if not keep_all_value or keep_value_on_attrs:
        remove_attr_session_override(prim, keep_value_on_attrs=keep_value_on_attrs)
    if prim.HasAttribute("module"):
        module = prim.GetAttribute("module")
        module.Set(mdl_path)
    else:
        source_asset = prim.GetAttribute("info:mdl:sourceAsset")
        if source_asset:
            stage = omni.usd.get_context().get_stage()
            shader_prim = UsdShade.Shader.Get(stage, prim.GetPath())
            shader_prim.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
            shader_prim.SetSourceAsset(Sdf.AssetPath(mdl_path), "mdl")
            _mtl_name = os.path.basename(
                mdl_path
                if not mdl_path.endswith(".mdl")
                else mdl_path.rpartition(".")[0]
            )
            shader_prim.SetSourceAssetSubIdentifier(_mtl_name, "mdl")
    load_mdl_parameters_for_prim([prim])
    carb.log_info(f"Replace MDL of material {prim.GetName()} to {mdl_path}")


# contains toolbar buttons for "convert to translucent" and "convert to opaque"
class MaterialButtonGroup(WidgetGroup):
    dataPath = ""
    def __init__(self, _dataPath):
        super().__init__()
        self.dataPath = _dataPath
        self._opaque_button = None
        self._translucent_button = None

    def clean(self):
        super().clean()
        self._opaque_button = None
        self._translucent_button = None

    def create(self, default_size):
        def on_opaque_clicked(*_):
            self._acquire_toolbar_context() 
            carb.log_error(f"opaqueMaterial")
            self._opaque_button.checked = False

            selectPrimPaths = omni.usd.get_context().get_selection().get_selected_prim_paths()

            capture_stage = omni.usd.get_context().get_stage()

            # convert the selected object(s) associated "shared material" to OPAQUE
            #   NB. preserve parameters so if the user switches back and forth, the previous params apply
            for path in selectPrimPaths:
                replace_shader(capture_stage.GetPrimAtPath(path), f"AperturePBR_Opacity.mdl", None, True)
                
        def on_translucent_clicked(*_):
            self._acquire_toolbar_context()
            carb.log_error(f"translucent")
            self._translucent_button.checked = False

            selectPrimPaths = omni.usd.get_context().get_selection().get_selected_prim_paths()

            capture_stage = omni.usd.get_context().get_stage()

            # convert the selected object(s) associated "shared material" to TRANSLUCENT
            #   NB. preserve parameters so if the user switches back and forth, the previous params apply
            for path in selectPrimPaths:
                replace_shader(capture_stage.GetPrimAtPath(path), f"AperturePBR_Translucent.mdl", None, False)

        self._opaque_button = ui.ToolButton( 
            name="opaqueMaterial", 
            tooltip="Convert to Opaque Material",
            width=default_size, 
            height=default_size,
            clicked_fn=on_opaque_clicked
        )

        self._translucent_button = ui.ToolButton( 
                name="translucentMaterial", 
                tooltip="Convert to Translucent Material",
                width=default_size, 
                height=default_size,
                clicked_fn=on_translucent_clicked
            )
        return {"opaqueMaterial": self._opaque_button, "translucentMaterial": self._translucent_button}

    def get_style(self):
        style = {
            "Button.Image::opaqueMaterial":      {"image_url": f"{self.dataPath}/toolbar_opaque_material.png"},
            "Button.Image::translucentMaterial": {"image_url": f"{self.dataPath}/toolbar_glass_material.png"}
        }
        return style

        
 
class LightspeedSetupExtension(omni.ext.IExt):
    def __init__(self):
        pass 

    def on_startup(self, ext_id): 
        # first set up the layout
        extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        workspace_file = f"{extension_path}/data/layout.default.json"
        result, _, content = omni.client.read_file(workspace_file)

        if result != omni.client.Result.OK:
            carb.log_error(f"Can't read the workspace file {workspace_file}, error code: {result}")
            return

        data = json.loads(memoryview(content).tobytes().decode("utf-8"))
        ui.Workspace.restore_workspace(data)

        # remove play button from main toolbar
        toolbar = omni.kit.window.toolbar.toolbar.get_instance()
        play_btn = omni.kit.window.toolbar.builtin_tools.play_button_group
        if toolbar and play_btn:
            toolbar.remove_widget(play_btn) 

        # add material tools    
        self.materialTools = MaterialButtonGroup(f"{extension_path}/data")  
        toolbar.add_widget(self.materialTools, 100)

    def on_shutdown(self):
        # cleanup the toolbar
        toolbar = omni.kit.window.toolbar.toolbar.get_instance()
        if toolbar and self.materialTools:
            toolbar.remove_widget(self.materialTools) 
        