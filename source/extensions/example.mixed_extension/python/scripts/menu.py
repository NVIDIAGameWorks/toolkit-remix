import carb
import carb.input
import omni.kit.editor
import omni.kit.ui
import omni.kit.commands
import carb.geometry
import random
import sys
from pxr import Usd, UsdGeom, Sdf, Gf, Tf, PhysicsSchema, PhysicsSchemaTools


ADD_FLEX_SCENE_MENU_ITEM = "Flex/Add/Flex Scene"
ADD_GROUND_PLANE_MENU_ITEM = "Flex/Add/Ground Plane"
ADD_MESH_GRID_MENU_ITEM = "Flex/Add/Grid Mesh"

SET_SOFTBODY_MENU_ITEM = "Flex/Set/Soft Body"
SET_CLOTH_MENU_ITEM = "Flex/Set/Cloth"
SET_COLLISION_MENU_ITEM = "Flex/Set/Collision"
SET_FLEX_ATTACHMENT_MENU_ITEM = "Flex/Set/Attachments"
SET_COOK_AS_COLLISION_MESH_MENU_ITEM = "Flex/Cook/Convex Decomposition"


class ClothData:
    def __init__(self, width=1.0, height=1.0, numWidth=50.0, numHeight=50.0):
        self.mWidth = width
        self.mHeight = height
        self.mNumWidth = numWidth
        self.mNumHeight = numHeight


def CreateMeshPoints(clothData, upAxis="Y"):
    points = []
    normals = []
    halfWidth = clothData.mWidth / 2.0
    halfHeight = clothData.mHeight / 2.0
    dx = clothData.mWidth / float(clothData.mNumWidth)
    dy = clothData.mHeight / float(clothData.mNumHeight)
    for h in range(0, clothData.mNumHeight + 1):
        y = -1.0 * halfHeight + h * dy
        for w in range(0, clothData.mNumWidth + 1):
            x = -1.0 * halfWidth + w * dx
            if upAxis == "Z":
                p = (x, y, 0)
            elif upAxis == "Y":
                p = (x, 0, y)
            else:
                p = (0, x, y)
            points.append(p)
    return points


def CreateFaceVertexCounts(clothData):
    faceVertexCount = []
    numFaces = clothData.mNumWidth * clothData.mNumHeight
    for i in range(0, numFaces):
        faceVertexCount.append(4)
    return faceVertexCount


def CreateFaceVertexIndices(clothData):
    faceVertexIndices = []
    dh = clothData.mNumWidth + 1
    for h in range(0, clothData.mNumHeight):
        for w in range(0, clothData.mNumWidth):
            idx1 = w + h * dh
            idx2 = (w + 1) + h * dh
            idx3 = (w + 1) + (h + 1) * dh
            idx4 = w + (h + 1) * dh
            faceVertexIndices.append(idx1)
            faceVertexIndices.append(idx2)
            faceVertexIndices.append(idx3)
            faceVertexIndices.append(idx4)
    return faceVertexIndices


def createMesh(stage, path, points, indices, vertexCounts):
    mesh = UsdGeom.Mesh.Define(stage, path)

    mesh.CreateFaceVertexCountsAttr().Set(vertexCounts)
    mesh.CreateFaceVertexIndicesAttr().Set(indices)
    mesh.CreatePointsAttr().Set(points)
    mesh.SetNormalsInterpolation("faceVarying")
    mesh.CreateDoubleSidedAttr().Set(True)
    mesh.CreateSubdivisionSchemeAttr().Set("none")

    return mesh


def addDefaultXforms(prim):
    xform = UsdGeom.Xformable(prim)
    xform_ops = []
    translateOp = xform.AddTranslateOp()
    xform_ops.append(translateOp)
    xform_ops.append(xform.AddOrientOp())
    xform_ops.append(xform.AddScaleOp())
    xform.SetXformOpOrder(xform_ops)


def CreateClothMesh(stage, upAxis, scaleFactor=1.0, resolutionPerAxis=30, color=None):
    prim_path = omni.kit.utils.get_stage_next_free_path(stage, "/clothMesh", True)
    mesh = UsdGeom.Mesh.Define(stage, prim_path)

    c = ClothData(scaleFactor, scaleFactor, resolutionPerAxis, resolutionPerAxis)

    points = CreateMeshPoints(c, upAxis)
    faceVertexCounts = CreateFaceVertexCounts(c)
    faceVertexIndices = CreateFaceVertexIndices(c)

    createMesh(stage, prim_path, points, faceVertexIndices, faceVertexCounts)

    if color is not None:
        mesh.CreateDisplayColorAttr().Set([color])

    meshPrim = stage.GetPrimAtPath(prim_path)
    addDefaultXforms(meshPrim)

    return prim_path


class FlexParameters:
    def __init__(
        self,
        gravity=(0, 0, -1000),
        dynamic_friction=0.5,
        radius=0.1,
        num_iterations=10,
        num_substeps=4,
        collision_distance=0.1,
        drag=0.0,
        lift=0,
        relaxation_factor=1.0,
        shape_collision_margin=0.25,
        particle_collision_margin=1,
        wind=(0, 0, 0),
        damping=0,
        max_speed=sys.float_info.max,
        plugin="flex",
    ):
        self.gravity = gravity
        self.dynamic_friction = dynamic_friction
        self.radius = radius
        self.num_iterations = num_iterations
        self.num_substeps = num_substeps
        self.collision_distance = collision_distance
        self.drag = drag
        self.lift = lift
        self.relaxation_factor = relaxation_factor
        self.shape_collision_margin = shape_collision_margin
        self.particle_collision_margin = particle_collision_margin
        self.wind = wind
        self.damping = damping
        self.max_speed = max_speed
        self.plugin = plugin


def addFlexScene(stage, physics_scene_path, params=FlexParameters()):
    physics_scene = stage.GetPrimAtPath(physics_scene_path)
    physics_scene.CreateAttribute("gravity", Sdf.ValueTypeNames.Float3, False).Set(params.gravity)
    physics_scene.CreateAttribute("flexDynamicFriction", Sdf.ValueTypeNames.Float, False).Set(params.dynamic_friction)
    physics_scene.CreateAttribute("radius", Sdf.ValueTypeNames.Float, False).Set(params.radius)
    physics_scene.CreateAttribute("numIterations", Sdf.ValueTypeNames.Int, False).Set(params.num_iterations)
    physics_scene.CreateAttribute("numSubsteps", Sdf.ValueTypeNames.Int, False).Set(params.num_substeps)
    physics_scene.CreateAttribute("collisionDistance", Sdf.ValueTypeNames.Float, False).Set(params.collision_distance)
    physics_scene.CreateAttribute("drag", Sdf.ValueTypeNames.Float, False).Set(params.drag)
    physics_scene.CreateAttribute("lift", Sdf.ValueTypeNames.Float, False).Set(params.lift)
    physics_scene.CreateAttribute("relaxationFactor", Sdf.ValueTypeNames.Float, False).Set(params.relaxation_factor)
    physics_scene.CreateAttribute("shapeCollisionMargin", Sdf.ValueTypeNames.Float, False).Set(
        params.shape_collision_margin
    )
    physics_scene.CreateAttribute("particleCollisionMargin", Sdf.ValueTypeNames.Float, False).Set(
        params.particle_collision_margin
    )
    physics_scene.CreateAttribute("wind", Sdf.ValueTypeNames.Float3, False).Set(params.wind)
    physics_scene.CreateAttribute("damping", Sdf.ValueTypeNames.Float, False).Set(params.damping)
    physics_scene.CreateAttribute("lift", Sdf.ValueTypeNames.Float, False).Set(params.lift)
    physics_scene.CreateAttribute("maxSpeed", Sdf.ValueTypeNames.Float, False).Set(params.max_speed)

    attr = physics_scene.CreateAttribute("plugin", Sdf.ValueTypeNames.Token, False, Sdf.VariabilityUniform)
    attr.Set("flex")
    attr.SetMetadata("allowedTokens", ["physx", "flex"])


def addPhysicsScene(stage, path, upAxis="Y"):
    metersPerUnit = UsdGeom.GetStageMetersPerUnit(stage)

    gravityScale = 10.0 / metersPerUnit
    gravity = Gf.Vec3f(0.0, 0.0, 0.0)

    if upAxis == "Y":
        gravity = Gf.Vec3f(0.0, -gravityScale, 0.0)
    elif upAxis == "Z":
        gravity = Gf.Vec3f(0.0, 0.0, -gravityScale)

    scene = PhysicsSchema.PhysicsScene.Define(stage, path)
    scene.CreateGravityAttr().Set(gravity)

    param = FlexParameters(gravity)
    param.collision_distance /= metersPerUnit
    param.radius /= metersPerUnit
    addFlexScene(stage, path, param)


def addSoftBodyPrim(
    stage, path, stretch_stiffness=1.0, bend_stiffness=0.5, collision_group=0, pressure_enabled=True, pressure=1.0
):
    soft = stage.DefinePrim(path + "/soft", "SoftBody")
    soft.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(stretch_stiffness)
    soft.CreateAttribute("bendStiffness", Sdf.ValueTypeNames.Float).Set(bend_stiffness)
    soft.CreateAttribute("collisionGroup", Sdf.ValueTypeNames.Int).Set(collision_group)
    if pressure_enabled:
        soft.CreateAttribute("pressure", Sdf.ValueTypeNames.Float).Set(pressure)
    soft.CreateRelationship("dynamicsMesh").AddTarget(path)
    return soft


def addFlexClothPrim(
    stage,
    path,
    renderMeshPath,
    stretch_stiffness=1.0,
    bend_stiffness=0.5,
    collision_group=0,
    pressure_enabled=True,
    pressure=1.0,
):
    soft = stage.DefinePrim(path + "/soft", "SoftBody")
    soft.CreateAttribute("stretchStiffness", Sdf.ValueTypeNames.Float).Set(stretch_stiffness)
    soft.CreateAttribute("bendStiffness", Sdf.ValueTypeNames.Float).Set(bend_stiffness)
    soft.CreateAttribute("collisionGroup", Sdf.ValueTypeNames.Int).Set(collision_group)
    soft.CreateRelationship("dynamicsMesh").AddTarget(renderMeshPath)
    soft.CreateRelationship("proxyMesh").AddTarget(path)
    soft.CreateAttribute("attachDistance", Sdf.ValueTypeNames.Float).Set(1.0)
    soft.CreateAttribute("attachEnabled", Sdf.ValueTypeNames.Bool).Set(True)
    return soft


def addPhysicsMaterial(stage, path, thickness=1.0, density=1.0):
    physMaterial = stage.DefinePrim(path + "/physMaterial", "physicsMaterial")
    physMaterial.CreateAttribute("thickness", Sdf.ValueTypeNames.Float).Set(thickness)
    physMaterial.CreateAttribute("density", Sdf.ValueTypeNames.Float).Set(density)
    return physMaterial


def addCollider(stage, prim, filter=0):
    if not prim.IsA(UsdGeom.Gprim):
        return

    collisionAPI = PhysicsSchema.CollisionAPI.Apply(prim)
    prim.CreateAttribute("filter", Sdf.ValueTypeNames.Int).Set(filter)
    collisionAPI.CreateCollisionEnabledAttr().Set(True)
    # 0.1 is the thickness. Setting it too big will explode the cloth
    materialPrim = addPhysicsMaterial(stage, str(prim.GetPath()), 0.1)
    prim.CreateRelationship("physicsMaterial").AddTarget(str(materialPrim.GetPath()))


def getUnitScaleFactor(stage):
    metersPerUnit = UsdGeom.GetStageMetersPerUnit(stage)
    scaleFactor = 1.0 / metersPerUnit
    return scaleFactor


class FlexMenu:
    def __init__(self, flex_interface):
        self._editor = omni.kit.editor.get_editor_interface()
        self._input = carb.input.acquire_input()
        self._flex = flex_interface

        self.menus = []

        self.menus.append(omni.kit.ui.get_editor_menu().add_item(ADD_FLEX_SCENE_MENU_ITEM, self._on_menu_click))
        self.menus.append(omni.kit.ui.get_editor_menu().add_item(ADD_GROUND_PLANE_MENU_ITEM, self._on_menu_click))
        self.menus.append(omni.kit.ui.get_editor_menu().add_item(ADD_MESH_GRID_MENU_ITEM, self._on_menu_click))
        self.menus.append(omni.kit.ui.get_editor_menu().add_item(SET_CLOTH_MENU_ITEM, self._on_menu_click))
        self.menus.append(omni.kit.ui.get_editor_menu().add_item(SET_COLLISION_MENU_ITEM, self._on_menu_click))
        self.menus.append(omni.kit.ui.get_editor_menu().add_item(SET_FLEX_ATTACHMENT_MENU_ITEM, self._on_menu_click))
        self.menus.append(
            omni.kit.ui.get_editor_menu().add_item(SET_COOK_AS_COLLISION_MESH_MENU_ITEM, self._on_menu_click)
        )

    #        self.menus.append(omni.kit.ui.get_editor_menu().add_item(SET_SOFTBODY_MENU_ITEM, self._on_menu_click))

    # Looking for proxy convex mesh, return true on success, flase otherwise.
    # Currently we only test against the first proxy mesh
    # TODO: need a more elegant way to get the job done
    def find_proxy_mesh(self, stage, input_path, proxy_name):
        proxy_path = input_path + "/" + proxy_name
        prim = stage.GetPrimAtPath(proxy_path)
        if prim:
            return True
        else:
            return False

    def _has_convex_hull(self, proxy_name):
        stage = self._stage
        selectedPrims = self._editor.get_selected_prim_paths()
        for path in selectedPrims:
            if self.find_proxy_mesh(stage, path, proxy_name):
                return True
        return False

    def _remove_convex_hull(self, proxy_name):
        stageId = self._editor.get_stage_id()
        selectedPrims = self._editor.get_selected_prim_paths()
        geometry = carb.geometry.acquire_geometry()
        for path in selectedPrims:
            geometry.removeConvexHull(stageId, path + "/" + proxy_name)

    def _create_convex_hull(self, max_convex_hulls, max_num_vertices_per_ch, resolution, proxy_name):
        stage = self._stage
        stageId = self._editor.get_stage_id()
        selectedPrims = self._editor.get_selected_prim_paths()
        geometry = carb.geometry.acquire_geometry()
        makeConvexHullsVisible = True
        for path in selectedPrims:
            num_convex_hulls = geometry.createConvexHull(
                stageId, path, proxy_name, max_convex_hulls, max_num_vertices_per_ch, resolution, makeConvexHullsVisible
            )
            if num_convex_hulls == 0:
                print("None convex hull generated!")

    def _create_convex_hull_skel_mesh(self, max_convex_hulls, max_num_vertices_per_ch, resolution, proxy_name):
        stage = self._stage
        stageId = self._editor.get_stage_id()
        selectedPrims = self._editor.get_selected_prim_paths()
        geometry = carb.geometry.acquire_geometry()
        makeConvexHullsVisible = True
        for path in selectedPrims:
            prim = stage.GetPrimAtPath(path)
            primRange = Usd.PrimRange(prim)
            for p in primRange:
                if p.IsA(UsdGeom.Mesh):
                    geometry.createConvexHullFromSkeletalMesh(
                        stageId,
                        str(p.GetPath()),
                        proxy_name,
                        max_convex_hulls,
                        max_num_vertices_per_ch,
                        resolution,
                        makeConvexHullsVisible,
                    )

    def _create_convex_hull_internal(self, proxy_name):
        self._popup_create_convex = omni.kit.ui.Popup("Create Collision Mesh", modal=True, width=800, height=100)
        self.max_convex_hulls = omni.kit.ui.FieldInt("Max Number of Convex Hulls ", 1)
        self.max_num_vertices_per_ch = omni.kit.ui.FieldInt("Max Number of Vertices per Convex Hull", 32)
        self.resolution = omni.kit.ui.FieldInt(
            "Maximum Number of Voxels Generated During the Voxelization Stage", 100000
        )
        self._popup_create_convex.layout.add_child(self.max_convex_hulls)
        self._popup_create_convex.layout.add_child(self.max_num_vertices_per_ch)
        self._popup_create_convex.layout.add_child(self.resolution)
        self.createConvexHullButton = omni.kit.ui.Button(f"Create")
        self.cancelConvexHullButton = omni.kit.ui.Button(f"Cancel")
        row_create_convex = omni.kit.ui.RowLayout()
        row_create_convex.add_child(self.createConvexHullButton)
        row_create_convex.add_child(self.cancelConvexHullButton)
        self._popup_create_convex.layout.add_child(row_create_convex)

        def _on_create_convex_hull_button_fn(widget):
            # Use _create_convex_hull for static mesh
            self._create_convex_hull_skel_mesh(
                self.max_convex_hulls.value, self.max_num_vertices_per_ch.value, self.resolution.value, proxy_name
            )
            self._popup_create_convex = None

        self.createConvexHullButton.set_clicked_fn(_on_create_convex_hull_button_fn)

        def _on_cancel_convex_hull_button_fn(widget):
            self._popup_create_convex = None

        self.cancelConvexHullButton.set_clicked_fn(_on_cancel_convex_hull_button_fn)

    def _create_collision_mesh(self, stage):
        self._stage = stage
        # If proxy meshes exist, ask user to choose whether to override it,
        # otherwise create proxy convex meshes
        proxy_name = "ConvexProxyMesh"
        if self._has_convex_hull(proxy_name):
            self._popup_warning = omni.kit.ui.Popup("Create Convex Hull", modal=True, width=500, height=10)
            self._popup_warning.layout.add_child(
                omni.kit.ui.Label("Convex hulls already exist, do you want to regenerate convex hull?")
            )
            self.yesButton = omni.kit.ui.Button(f"Yes")
            self.noButton = omni.kit.ui.Button(f"No")
            row_choose = omni.kit.ui.RowLayout()
            row_choose.add_child(self.yesButton)
            row_choose.add_child(self.noButton)
            self._popup_warning.layout.add_child(row_choose)

            def _on_yes_button_fn(widget):
                self._remove_convex_hull(proxy_name)
                self._create_convex_hull_internal(proxy_name)
                self._popup_warning = None

            self.yesButton.set_clicked_fn(_on_yes_button_fn)

            def _on_no_button_fn(widget):
                self._popup_warning = None

            self.noButton.set_clicked_fn(_on_no_button_fn)
        else:
            self._create_convex_hull_internal(proxy_name)

    def _on_menu_click(self, menu, value):
        stage = self._editor.get_stage()
        defaultPrimPath = str(stage.GetDefaultPrim().GetPath())
        selectedPrims = self._editor.get_selected_prim_paths()
        upAxis = UsdGeom.GetStageUpAxis(stage)
        scaleFactor = getUnitScaleFactor(stage)
        geometry = carb.geometry.acquire_geometry()
        stageId = self._editor.get_stage_id()

        if menu == ADD_FLEX_SCENE_MENU_ITEM:
            addPhysicsScene(stage, defaultPrimPath + "/physicsScene", upAxis)
        elif menu == ADD_GROUND_PLANE_MENU_ITEM:
            PhysicsSchemaTools.addGroundPlane(
                stage, defaultPrimPath, upAxis, 25.0 * scaleFactor, Gf.Vec3f(0.0), Gf.Vec3f(0.5)
            )
        # elif (menu == SET_SOFTBODY_MENU_ITEM):
        #    for path in selectedPrims:
        #        addSoftBodyPrim(stage, path)
        elif menu == SET_COLLISION_MENU_ITEM:
            for path in selectedPrims:
                prim = stage.GetPrimAtPath(path)
                for child in Usd.PrimRange(prim):
                    addCollider(stage, child)
        elif menu == SET_CLOTH_MENU_ITEM:
            for path in selectedPrims:
                # a temp path as a place holder for the triangulated Mesh Prim
                tmpPath = omni.kit.utils.get_stage_next_free_path(stage, defaultPrimPath, True)
                if geometry.triangulate(stageId, path, tmpPath):
                    # get the triangulated mesh prim
                    triMeshPrim = stage.GetPrimAtPath(tmpPath)
                    # Prim path for the final softbody mesh prim
                    proxyMeshPath = path + "/ProxyMesh"
                    # create softbody triangulate mesh prim
                    proxyMesh = UsdGeom.Mesh.Define(stage, proxyMeshPath)
                    # PhysicsSchema.CollisionAPI.Apply(stage.GetPrimAtPath(proxyMeshPath))
                    # # apply CollisionAPI to this triangulate mesh prim
                    proxyMesh.CreatePointsAttr().Set(UsdGeom.Mesh.Get(stage, tmpPath).GetPointsAttr().Get())
                    proxyMesh.CreateNormalsAttr().Set(UsdGeom.Mesh.Get(stage, tmpPath).GetNormalsAttr().Get())
                    proxyMesh.CreateFaceVertexCountsAttr().Set(
                        UsdGeom.Mesh.Get(stage, tmpPath).GetFaceVertexCountsAttr().Get()
                    )
                    proxyMesh.CreateFaceVertexIndicesAttr().Set(
                        UsdGeom.Mesh.Get(stage, tmpPath).GetFaceVertexIndicesAttr().Get()
                    )
                    proxyMesh.CreatePurposeAttr().Set(UsdGeom.Tokens.guide)
                    # make the new mesh softbody
                    addFlexClothPrim(stage, proxyMeshPath, path)
                    # time to remove the place holder prim
                    stage.RemovePrim(triMeshPrim.GetPath())

        elif menu == ADD_MESH_GRID_MENU_ITEM:
            self._add_grid_mesh(stage, scaleFactor, upAxis)
        elif menu == SET_FLEX_ATTACHMENT_MENU_ITEM:
            for path in selectedPrims:
                prim = stage.GetPrimAtPath(path)
                prim.CreateAttribute("enableAttachment", Sdf.ValueTypeNames.Bool, False).Set(True)
        elif menu == SET_COOK_AS_COLLISION_MESH_MENU_ITEM:
            self._create_collision_mesh(stage)

    def _select_and_focus(self, path):
        self._editor.set_prim_path_selected(path, True, False, True, True)

    def _createGridMesh(self, scaleFactor, resolution):
        path = CreateClothMesh(self._stage, self._upAxis, scaleFactor, resolution, Gf.Vec3f(1.0, 0.0, 0.0))
        self._select_and_focus(path)

    def _add_grid_mesh(self, stage, unitScaleFactor, upAxis):
        self._stage = stage
        self._upAxis = upAxis
        self._unitScaleFactor = unitScaleFactor

        self._popup = omni.kit.ui.Popup("Create Grid Mesh", modal=True, width=300, height=100)
        self.scaleField = omni.kit.ui.FieldDouble("Scale", 2.0)
        self.resolutionField = omni.kit.ui.FieldInt("Resolution", 50)
        self._popup.layout.add_child(self.scaleField)
        self._popup.layout.add_child(self.resolutionField)
        self.createButton = omni.kit.ui.Button(f"Create")
        self.cancelButton = omni.kit.ui.Button(f"Cancel")
        row = omni.kit.ui.RowLayout()
        row.add_child(self.createButton)
        row.add_child(self.cancelButton)
        self._popup.layout.add_child(row)

        def _on_create_button_fn(widget):
            scaleFactor = self.scaleField.value * self._unitScaleFactor
            resolution = self.resolutionField.value
            self._createGridMesh(scaleFactor, resolution)
            self._popup = None

        self.createButton.set_clicked_fn(_on_create_button_fn)

        def _on_cancel_button_fn(widget):
            self._popup = None

        self.cancelButton.set_clicked_fn(_on_cancel_button_fn)

    def shutdown(self):
        self.menus = []
