"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import subprocess
import traceback
from pathlib import Path

import carb
import omni.usd
from lightspeed.common import ReferenceEdit, constants
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from lightspeed.tool.octahedral_converter import LightspeedOctahedralConverter
from omni.kit.window.popup_dialog import MessageDialog
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


class LightspeedPosProcessExporter:
    def __init__(self):
        self._nvtt_path = Path(constants.NVTT_PATH)
        self.__layer_manager = LayerManagerCore()

    def _remove_extra_attr(self, prim: Usd.Prim):
        white_list = {
            "normals",
            "points",
            "doubleSided",
            "orientation",
            "invertedUvs",
            "material:binding",
            # below values are kept for kit compatibility, but not needed by dxvk_rt
            "faceVertexCounts",
            "faceVertexIndices",
            "primvars:st",
            "primvars:st:indices",
            "subdivisionScheme",  # needed for smooth normals when using vertex interpolation
        }

        attr_to_remove = []
        for attr in prim.GetAttributes():
            if attr.GetName() not in white_list:
                attr_to_remove.append(attr.GetName())

        for attr in attr_to_remove:
            prim.RemoveProperty(attr)

    def _process_uvs(self, prim: Usd.Prim):
        # get the primvars API of the prim
        gp_pv = UsdGeom.PrimvarsAPI(prim)
        # get the primvars attribute of the UVs
        st_prim_var = gp_pv.GetPrimvar("st")

        # [AJAUS] Because USD and Directx8/9 assume different texture coordinate origins,
        # invert the vertical texture coordinate
        flattened_uvs = st_prim_var.ComputeFlattened()
        inverted_uvs = []
        for uv_value in flattened_uvs:
            inverted_uvs.append(Gf.Vec2f(uv_value[0], -uv_value[1]))

        prim.CreateAttribute("invertedUvs", Sdf.ValueTypeNames.Float2Array, False).Set(inverted_uvs)

    def _triangulate_mesh(self, prim: Usd.Prim):
        # indices and faces converted to triangles
        mesh = UsdGeom.Mesh(prim)
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        faces = mesh.GetFaceVertexCountsAttr().Get()

        triangles = []
        if not indices or not faces:
            return triangles

        indices_offset = 0
        new_face_counts = []

        subsets = []

        # need to update geom subset face lists
        display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        children_iterator = iter(Usd.PrimRange(mesh.GetPrim(), display_predicate))
        for child_prim in children_iterator:
            if child_prim.IsA(UsdGeom.Subset):
                subset = UsdGeom.Subset.Get(omni.usd.get_context().get_stage(), child_prim.GetPath())
                subsets.append(
                    {
                        "subset": subset,
                        "old_faces": set(subset.GetIndicesAttr().Get()),  # set of old face indices in this subset
                        "new_faces": [],  # the new face index list
                    }
                )

        for old_face_index, face_count in enumerate(faces):
            start_index = indices[indices_offset]
            for face_index in range(face_count - 2):
                for subset in subsets:
                    if old_face_index in subset["old_faces"]:
                        subset["new_faces"].append(len(new_face_counts))
                new_face_counts.append(3)
                index1 = indices_offset + face_index + 1
                index2 = indices_offset + face_index + 2
                triangles.append(start_index)
                triangles.append(indices[index1])
                triangles.append(indices[index2])
            indices_offset += face_count

        for subset in subsets:
            subset["subset"].GetIndicesAttr().Set(subset["new_faces"])

        mesh.GetFaceVertexIndicesAttr().Set(triangles)
        mesh.GetFaceVertexCountsAttr().Set(new_face_counts)
        return triangles

    def _align_vertex_data(self, prim: Usd.Prim):
        # get the mesh schema API from the Prim
        mesh_schema = UsdGeom.Mesh(prim)

        face_vertex_indices = mesh_schema.GetFaceVertexIndicesAttr().Get()
        points = mesh_schema.GetPointsAttr().Get()

        primvar_api = UsdGeom.PrimvarsAPI(prim)
        geom_tokens = [UsdGeom.Tokens.faceVarying, UsdGeom.Tokens.varying, UsdGeom.Tokens.vertex]
        primvars = [
            {
                "primvar": primvar,
                "values": primvar.ComputeFlattened(),
                "fixed_values": [],
                "interpolation": primvar.GetInterpolation(),
            }
            for primvar in primvar_api.GetPrimvars()
            if primvar.GetInterpolation() in geom_tokens
        ]

        fixed_indices = range(0, len(face_vertex_indices))
        fixed_points = []
        for i in fixed_indices:
            fixed_points.append(points[face_vertex_indices[i]])

        for primvar in primvars:
            if primvar["interpolation"] == UsdGeom.Tokens.vertex:
                for i in fixed_indices:
                    primvar["fixed_values"].append(primvar["values"][face_vertex_indices[i]])

        fixed_normals = []
        normals_interp = mesh_schema.GetNormalsInterpolation()
        normals = mesh_schema.GetNormalsAttr().Get()
        if normals_interp == UsdGeom.Tokens.vertex and normals:
            # Normals are currently in the (old) vertex order.  need to expand them to be 1 normal per vertex per face
            for i in fixed_indices:
                fixed_normals.append(normals[face_vertex_indices[i]])
            mesh_schema.GetNormalsAttr().Set(normals)
        else:
            # Normals are already in 1 normal per vertex per face, need to set it to vertex so that triangulation
            # doesn't break it.
            mesh_schema.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

        mesh_schema.GetFaceVertexIndicesAttr().Set(fixed_indices)
        mesh_schema.GetPointsAttr().Set(fixed_points)
        for primvar in primvars:
            if primvar["interpolation"] == UsdGeom.Tokens.vertex:
                primvar["values"] = primvar["fixed_values"]
            primvar["primvar"].Set(primvar["values"])
            primvar["primvar"].BlockIndices()
            primvar["primvar"].SetInterpolation(UsdGeom.Tokens.vertex)

    def _process_subsets(self, prim: Usd.Prim):
        mesh_schema = UsdGeom.Mesh(prim)
        face_vertex_indices = mesh_schema.GetFaceVertexIndicesAttr().Get()
        display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        children_iterator = iter(Usd.PrimRange(prim, display_predicate))
        for child_prim in children_iterator:
            if child_prim.IsA(UsdGeom.Subset):
                subset = UsdGeom.Subset.Get(omni.usd.get_context().get_stage(), child_prim.GetPath())
                face_indices = subset.GetIndicesAttr().Get()
                vert_indices = []
                for face_index in face_indices:
                    vert_indices.append(face_vertex_indices[face_index * 3 + 0])
                    vert_indices.append(face_vertex_indices[face_index * 3 + 1])
                    vert_indices.append(face_vertex_indices[face_index * 3 + 2])
                child_prim.CreateAttribute("triangleIndices", Sdf.ValueTypeNames.IntArray).Set(vert_indices)

    def _bake_geom_prim_xforms_in_mesh(self, prim: Usd.Prim):
        parent_prim = prim
        while (
            parent_prim.IsValid()
            and parent_prim.GetParent().IsValid()
            and (parent_prim.GetParent().GetPath() != Sdf.Path("/RootNode/meshes"))
        ):
            parent_prim = parent_prim.GetParent()
        if not parent_prim.IsValid():
            prim_path_str = str(prim.GetPath())
            carb.log_error("Could not resolve mesh Xform parent for: " + prim_path_str)

            class MeshXformParentUnresolveableError(Exception):
                pass

            raise MeshXformParentUnresolveableError()
        xform = UsdGeom.XformCache().ComputeRelativeTransform(prim, parent_prim)[0]

        # get the mesh schema API from the Prim
        mesh_schema = UsdGeom.Mesh(prim)

        # Points/Vertices
        points_attr = mesh_schema.GetPointsAttr()
        points_arr = points_attr.Get()
        new_points_arr = []
        for tri in points_arr:
            new_tri = xform.TransformAffine(tri)
            new_points_arr.append(new_tri)
        points_attr.Set(new_points_arr)

        # Normals
        normals_attr = mesh_schema.GetNormalsAttr()
        normals_arr = normals_attr.Get()
        if normals_arr:
            new_normals_arr = []
            for normal in normals_arr:
                new_normal = xform.GetInverse().GetTranspose().TransformAffine(normal)
                new_normals_arr.append(new_normal)
            normals_attr.Set(new_normals_arr)

    def _process_mesh_prim(self, prim: Usd.Prim):
        # processing steps:
        # * Freeze transforms
        # * Strip unused attributes
        # * Align all per vertex data
        #   * computeFlattened for all primvars
        #   * split all faces to have their own vertices
        #     * faceVertexIndices should become 0,1,...,n
        #     * all primvars should get index arrays matchign faceVertexIndices
        # * triangulate any faces with > 3 vertices
        #   * triangles that came from the same face will share verts
        #   * geom subsets will be updated to point to the correct faces
        # * create inverted UVs
        # * add triangleIndices for geom subsets

        # Freeze Transforms:
        # runtime does not support transforms on prims/meshes, as they are wasteful
        #   so we bake them into vertices and normals
        # IMPORTANT: this must be run before _remove_extra_attr, or  else the relevant
        #   xform info will be stripped
        self._bake_geom_prim_xforms_in_mesh(prim)

        # strip out  attributes that the runtime doesn't support
        self._remove_extra_attr(prim)

        # Runtime only supports a single array of verts, with each vertex having position, normal, uv, etc.
        # Thus, we need to make all of the per-vertex data arrays the same length and ordering. As FaceVarying
        # primvars can have the most information (3 points of data per triangle), all data arrays have to be expanded
        # to match that.
        self._align_vertex_data(prim)

        # split any non-triangle faces into triangles (updates indices of all indexed data)
        # As this introduces new faces, this must also update any geom subsets.
        self._triangulate_mesh(prim)

        # Make a new attribute for dxvk_rt compatible uvs:
        # 3 uvs per triangle, in the same order as the positions, with the uv.y coordinate inverted.
        self._process_uvs(prim)

        # subsets store face indices, but dxvk_rt needs triangle indices.
        self._process_subsets(prim)

    def _process_shader_prim(self, prim):
        # convert tangent space normal maps to octahedral
        normal_map_encoding_attr = prim.GetAttribute(constants.MATERIAL_INPUTS_NORMALMAP_ENCODING)
        normal_map_attr = prim.GetAttribute(constants.MATERIAL_INPUTS_NORMALMAP_TEXTURE)
        if (
            normal_map_attr
            and normal_map_encoding_attr
            and normal_map_encoding_attr.HasValue()
            and normal_map_attr.HasValue
        ):
            encoding = normal_map_encoding_attr.Get()
            if encoding != constants.NormalMapEncodings.OCTAHEDRAL.value:
                # need to re-encode normal map
                normal_path = normal_map_attr.Get()
                if normal_path:
                    abs_path = Path(normal_path.resolvedPath)
                    rel_path = Path(normal_path.path)
                    new_abs_path = abs_path.with_name(abs_path.stem + "_OTH" + abs_path.suffix)
                    new_rel_path = rel_path.with_name(rel_path.stem + "_OTH" + rel_path.suffix)
                    if encoding == constants.NormalMapEncodings.TANGENT_SPACE_DX.value:
                        LightspeedOctahedralConverter.convert_dx_file_to_octahedral(str(abs_path), str(new_abs_path))
                    elif encoding == constants.NormalMapEncodings.TANGENT_SPACE_OGL.value:
                        LightspeedOctahedralConverter.convert_ogl_file_to_octahedral(str(abs_path), str(new_abs_path))
                    normal_map_attr.Set(str(new_rel_path))
                    normal_map_encoding_attr.Set(constants.NormalMapEncodings.OCTAHEDRAL.value)

        # compress png textures to dds
        for attr_name, bc_mode in constants.TEXTURE_COMPRESSION_LEVELS.items():
            attr = prim.GetAttribute(attr_name)
            if attr and attr.Get():
                abs_path = Path(attr.Get().resolvedPath)
                rel_path = Path(attr.Get().path)
                if abs_path and abs_path.suffix.lower() != ".dds":
                    dds_path = abs_path.with_suffix(".dds")
                    rel_dds_path = rel_path.with_suffix(".dds")
                    # only create the dds if it doesn't already exist
                    if not dds_path.exists():
                        compress_mip_process = subprocess.Popen(  # noqa
                            [str(self._nvtt_path), str(abs_path), "--format", bc_mode, "--output", str(dds_path)]
                        )
                        compress_mip_process.wait()

                    attr.Set(str(rel_dds_path))
                    # NOTE: not safe to delete the original png here, as any other prims re-using the texture will fail
                    # to resolve the absolute path if the file no longer exists.
                    # os.remove(abs_path)

    async def process(self, export_file_path, progress_text_callback, progress_callback):
        carb.log_info("Processing: " + export_file_path)

        context = omni.usd.get_context()

        # TODO: Crash, use async function instead, waiting OM-42168
        # success = context.open_stage(export_file_path)
        result, _ = await context.open_stage_async(export_file_path)
        if not result:
            return

        export_stage = context.get_stage()

        # flatten all layers
        export_replacement_layer = self.__layer_manager.get_layer_instance(LayerType.replacement)
        if export_replacement_layer is None:
            carb.log_error("Can't find the replacement layer")
            return
        export_replacement_layer.flatten_sublayers()

        # process meshes
        # TraverseAll because we want to grab overrides
        all_geos = [prim_ref for prim_ref in export_stage.TraverseAll() if UsdGeom.Mesh(prim_ref)]
        failed_processes = []
        # TODO a crash in one geo shouldn't prevent processing the rest of the geometry
        length = len(all_geos)
        for i, geo_prim in enumerate(all_geos):
            carb.log_info(f"Post Processing Mesh: {geo_prim.GetPath()}")
            progress_text_callback(f"Post Processing Mesh:\n{geo_prim.GetPath()}")
            progress_callback(float(i) / length)
            await omni.kit.app.get_app().next_update_async()
            try:
                # apply edits to the geo prim in it's source usd, not in the top level replacements.usd
                with ReferenceEdit(geo_prim):
                    self._process_mesh_prim(geo_prim)
            except Exception as e:  # noqa
                failed_processes.append(str(geo_prim.GetPath()))
                carb.log_error("Exception when post-processing mesh: " + str(geo_prim.GetPath()))
                carb.log_error(f"{e}")
                carb.log_error(f"{traceback.format_exc()}")

        # process materials
        # TraverseAll because we want to grab overrides
        all_shaders = [prim_ref for prim_ref in export_stage.TraverseAll() if prim_ref.IsA(UsdShade.Shader)]
        # TODO a crash in one shader shouldn't prevent processing the rest of the materials
        i = 0.0
        length = len(all_shaders)
        for i, shader_prim in enumerate(all_shaders):
            carb.log_info(f"Post Processing Shader: {shader_prim.GetPath()}")
            progress_text_callback(f"Post Processing Shader:\n{shader_prim.GetPath()}")
            progress_callback(float(i) / length)
            await omni.kit.app.get_app().next_update_async()
            try:
                if export_replacement_layer.get_sdf_layer().GetPrimAtPath(shader_prim.GetPath()):
                    # top level replacements already has opinions about this shader, so apply edits in replacements.
                    self._process_shader_prim(shader_prim)
                else:
                    # Shader is just referenced from another USD, so apply edits to the source usd
                    with ReferenceEdit(shader_prim):
                        self._process_shader_prim(shader_prim)
            except Exception as e:  # noqa
                failed_processes.append(str(shader_prim.GetPath()))
                carb.log_error("Exception when post-processing shader: " + str(shader_prim.GetPath()))
                carb.log_error(f"{e}")
                carb.log_error(f"{traceback.format_exc()}")

        await context.save_stage_async()

        if failed_processes:

            def on_okay_clicked(dialog: MessageDialog):
                dialog.hide()

            message = (
                "Prims failed to export properly.  The contents of gameReadyAssets are probably invalid."
                "\nError details have been printed to the console."
                "\n\nFailing prims: \n  " + ",\n  ".join(failed_processes)
            )

            dialog = MessageDialog(
                width=600,
                message=message,
                ok_handler=on_okay_clicked,
                ok_label="Okay",
                disable_cancel_button=True,
            )
            dialog.show()
