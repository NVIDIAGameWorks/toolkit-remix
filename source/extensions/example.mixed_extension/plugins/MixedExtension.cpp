// Copyright (c) 2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//

// clang-format off
#include "../../../plugins/common/UsdPCH.h"
// clang-format on

#define CARB_EXPORTS
#include <carb/flex/Flex.h>

#include <carb/Framework.h>
#include <carb/PluginUtils.h>
#include <carb/interop/Interop.h>
#include <carb/settings/ISettings.h>
#include <carb/logging/Log.h>
#include <carb/fastcache/FastCache.h>

#include <omni/kit/IStageUpdate.h>

#include <NvFlex.h>
#include <NvFlexExt.h>

#define GLM_ENABLE_EXPERIMENTAL
#include <glm/glm/glm.hpp>
#include <glm/glm/gtx/quaternion.hpp>

#include "FlexUtil.h"

#if CARB_PLATFORM_WINDOWS
//#    pragma warning(push)
#    pragma warning(disable : 4244) // = Conversion from double to float / int to float
#    pragma warning(disable : 4267) // conversion from size_t to int
#    pragma warning(disable : 4305) // argument truncation from double to float
#    pragma warning(disable : 4800) // int to bool
#    pragma warning(disable : 4996) // call to std::copy with parameters that may be unsafe
#    define NOMINMAX // Make sure nobody #defines min or max
#endif

#define FLEX_PROFILE false
#define NON_SMOOTH_NORMAL_HACK true

const struct carb::PluginImplDesc kPluginImpl = { "omni.flex.plugin", "Flex", "NVIDIA",
                                                  carb::PluginHotReload::eDisabled, "dev" };
CARB_PLUGIN_IMPL(kPluginImpl, carb::flex::Flex)
CARB_PLUGIN_IMPL_DEPS(carb::settings::ISettings, carb::fastcache::FastCache, carb::interop::Interop)

namespace carb
{

namespace flex
{

namespace
{
carb::settings::ISettings* iSettings = nullptr;
carb::fastcache::FastCache* iFastCache = nullptr;

static pxr::UsdStageRefPtr g_stage = nullptr;
static bool g_needResync = false;


// fwd
struct FlexContext;
bool ParsePrim(long int stageId, const pxr::UsdPrim& prim, FlexContext* context);


struct FlexAttachment
{
    int particleIndex;

    pxr::UsdPrim parent;
    pxr::GfVec3f localOffset;

    float originalMass;
};

void CreateAttachments(pxr::UsdStagePtr stage,
                       glm::vec4* particles,
                       int numParticles,
                       float attachDistance,
                       std::vector<FlexAttachment>& attachments)
{
    pxr::UsdPrimRange range = stage->Traverse();

    for (pxr::UsdPrimRange::iterator iter = range.begin(); iter != range.end(); ++iter)
    {
        pxr::UsdPrim prim = *iter;

        // skip prims that don't have an attach attribute set
        bool attachEnabled = false;

        if (pxr::UsdAttribute attr = prim.GetAttribute(pxr::TfToken("enableAttachment")))
            attr.Get(&attachEnabled);

        if (!attachEnabled)
            continue;

        // todo: avoid computing world to local multiple times for each soft body
        pxr::UsdGeomXform xform(prim);

        pxr::GfMatrix4f localToWorld = pxr::GfMatrix4f(xform.ComputeLocalToWorldTransform(pxr::UsdTimeCode::Default()));
        pxr::GfMatrix4f worldToLocal = localToWorld.GetInverse();

        for (int i = 0; i < numParticles; ++i)
        {
            pxr::GfVec3f worldPos = pxr::GfVec3f(particles[i].x, particles[i].y, particles[i].z);
            pxr::GfVec3f localPos = worldToLocal.Transform(worldPos);

            float d = FLT_MAX;

            if (strcmp(prim.GetTypeName().GetText(), "Sphere") == 0)
            {
                pxr::UsdGeomSphere sphere(prim);

                double radius = 1.0f;
                sphere.GetRadiusAttr().Get(&radius);

                pxr::GfVec3f cp = localToWorld.Transform(ClosestPointToSphere(localPos, radius));

                d = (cp - worldPos).GetLength();
            }
            else if (strcmp(prim.GetTypeName().GetText(), "Cube") == 0)
            {
                pxr::UsdGeomCube cube(prim);

                pxr::GfVec3d extents(2.0f, 2.0f, 2.0f);
                cube.GetSizeAttr().Get(&extents);

                pxr::GfVec3f cp = localToWorld.Transform(
                    ClosestPointToBox(localPos, -pxr::GfVec3f(extents) * 0.5f, pxr::GfVec3f(extents) * 0.5f));

                d = (cp - worldPos).GetLength();
            }
            else if (strcmp(prim.GetTypeName().GetText(), "Capsule") == 0)
            {
                pxr::UsdGeomCapsule capsule(prim);

                // must be double or will not read attr correctly
                double height = 1.0f;
                double radius = 0.5f;

                ReadAttribute(prim, "height", &height);
                ReadAttribute(prim, "radius", &radius);

                float halfHeight = height * 0.5f;
                pxr::GfVec3f axis(0.0f, 0.0f, 1.0f);

                pxr::GfVec3f cp = localToWorld.Transform(
                    ClosestPointToCapsule(localPos, -halfHeight * axis, halfHeight * axis, radius));

                d = (cp - worldPos).GetLength();
            }

            // create attach constraint if within cutoff distance
            if (d < attachDistance)
            {
                FlexAttachment attach;
                attach.localOffset = localPos;
                attach.parent = prim;
                attach.particleIndex = i;
                attach.originalMass = particles[i].w;

                // fix particle
                particles[i].w = 0.0f;

                attachments.push_back(attach);
            }
        }
    }
}

void UpdateAttachments(const std::vector<FlexAttachment>& attachments, bool enabled, glm::vec4* particles, int numParticles)
{
    for (size_t i = 0; i < attachments.size(); ++i)
    {
        const FlexAttachment& attach = attachments[i];

        if (enabled)
        {
            pxr::GfMatrix4d localToWorld = GetWorldTransform(attach.parent);
            pxr::GfVec3f p = localToWorld.Transform(attach.localOffset);

            particles[attach.particleIndex].x = p[0];
            particles[attach.particleIndex].y = p[1];
            particles[attach.particleIndex].z = p[2];
        }
        else
        {
            // reset particle mass
            particles[attach.particleIndex].w = attach.originalMass;
        }
    }
}

struct FlexSoftBody
{
    int particleOffset;
    int particleCount;

    int triangleOffset;
    int triangleCount;

    int tetraOffset;
    int tetraCount;

    int inflatableOffset = -1;

    // associated primitive
    pxr::UsdPrim softbody;

    pxr::UsdGeomMesh simGeo;
    pxr::UsdGeomMesh renderGeo;

    std::vector<FlexAttachment> attachments;
    bool attachmentsEnabled = true;
};

struct FlexRigidBody
{
    pxr::UsdPrim xform;
    int rigidIndex;

    int rigidShapeOffset;
    int rigidShapeCount;
};

struct FlexRigidMaterial
{
    pxr::UsdPrim source;

    NvFlexRigidMaterial surface;

    float thickness;
    float density;
};

struct FlexBuffers
{
    // particle data
    NvFlexVector<glm::vec4> positions;
    NvFlexVector<glm::vec4> restPositions;
    NvFlexVector<glm::vec3> velocities;
    NvFlexVector<int> phases;
    NvFlexVector<float> densities;
    NvFlexVector<glm::vec4> anisotropy1;
    NvFlexVector<glm::vec4> anisotropy2;
    NvFlexVector<glm::vec4> anisotropy3;
    NvFlexVector<glm::vec4> normals;
    NvFlexVector<glm::vec4> smoothPositions;
    NvFlexVector<glm::vec4> diffusePositions;
    NvFlexVector<glm::vec4> diffuseVelocities;
    NvFlexVector<int> diffuseCount;

    NvFlexVector<int> activeIndices;

    // static geometry
    NvFlexVector<NvFlexCollisionGeometry> shapeGeometry;
    NvFlexVector<glm::vec4> shapePositions;
    NvFlexVector<glm::quat> shapeRotations;
    NvFlexVector<glm::vec4> shapePrevPositions;
    NvFlexVector<glm::quat> shapePrevRotations;
    NvFlexVector<int> shapeFlags;

    // shape matching
    NvFlexVector<int> shapeMatchingOffsets;
    NvFlexVector<int> shapeMatchingIndices;
    NvFlexVector<int> shapeMatchingMeshSize;
    NvFlexVector<float> shapeMatchingCoefficients;
    NvFlexVector<float> shapeMatchingPlasticThresholds;
    NvFlexVector<float> shapeMatchingPlasticCreeps;
    NvFlexVector<glm::quat> shapeMatchingRotations;
    NvFlexVector<glm::vec3> shapeMatchingTranslations;
    NvFlexVector<glm::vec3> shapeMatchingLocalPositions;
    NvFlexVector<glm::vec4> shapeMatchingLocalNormals;

    // inflatables
    NvFlexVector<int> inflatableTriOffsets;
    NvFlexVector<int> inflatableTriCounts;
    NvFlexVector<float> inflatableVolumes;
    NvFlexVector<float> inflatableCoefficients;
    NvFlexVector<float> inflatablePressures;

    // springs
    NvFlexVector<int> springIndices;
    NvFlexVector<float> springLengths;
    NvFlexVector<float> springStiffness;

    // rigid to Particle attachment
    NvFlexVector<NvFlexRigidParticleAttachment> rigidParticleAttachments;

    // tetrahedra
    NvFlexVector<int> tetraIndices;
    NvFlexVector<glm::mat3> tetraRestPoses;
    NvFlexVector<float> tetraStress;
    NvFlexVector<int> tetraMaterialIndices;
    NvFlexVector<glm::vec4> tetraFiberDirections;

    std::vector<NvFlexFEMMaterial> tetraMaterials;

    // rigid bodies
    NvFlexVector<NvFlexRigidBody> rigidBodies;
    NvFlexVector<NvFlexRigidShape> rigidShapes;
    NvFlexVector<NvFlexRigidJoint> rigidJoints;

    // Cables
    NvFlexVector<NvFlexCableLink> cableLinks;
    NvFlexVector<NvFlexMuscleTendon> muscles;

    // cloth mesh
    NvFlexVector<int> triangles;
    NvFlexVector<glm::vec3> triangleNormals;
    NvFlexVector<int> triangleFeatures;

    NvFlexVector<glm::vec3> uvs;

    FlexBuffers(NvFlexLibrary* l)
        : positions(l),
          restPositions(l),
          velocities(l),
          phases(l),
          densities(l),
          anisotropy1(l),
          anisotropy2(l),
          anisotropy3(l),
          normals(l),
          smoothPositions(l),
          diffusePositions(l),
          diffuseVelocities(l),
          diffuseCount(l),
          activeIndices(l),
          shapeGeometry(l),
          shapePositions(l),
          shapeRotations(l),
          shapePrevPositions(l),
          shapePrevRotations(l),
          shapeFlags(l),
          shapeMatchingOffsets(l),
          shapeMatchingIndices(l),
          shapeMatchingMeshSize(l),
          shapeMatchingCoefficients(l),
          shapeMatchingPlasticThresholds(l),
          shapeMatchingPlasticCreeps(l),
          shapeMatchingRotations(l),
          shapeMatchingTranslations(l),
          shapeMatchingLocalPositions(l),
          shapeMatchingLocalNormals(l),
          inflatableTriOffsets(l),
          inflatableTriCounts(l),
          inflatableVolumes(l),
          inflatableCoefficients(l),
          inflatablePressures(l),
          springIndices(l),
          springLengths(l),
          springStiffness(l),
          rigidParticleAttachments(l),
          tetraIndices(l),
          tetraRestPoses(l),
          tetraStress(l),
          tetraMaterialIndices(l),
          tetraFiberDirections(l),
          rigidBodies(l),
          rigidShapes(l),
          rigidJoints(l),
          cableLinks(l),
          muscles(l),
          triangles(l),
          triangleNormals(l),
          triangleFeatures(l),
          uvs(l)
    {
    }


    void MapBuffers()
    {
        positions.map();
        restPositions.map();
        velocities.map();
        phases.map();
        densities.map();
        anisotropy1.map();
        anisotropy2.map();
        anisotropy3.map();
        normals.map();
        diffusePositions.map();
        diffuseVelocities.map();
        diffuseCount.map();
        smoothPositions.map();
        activeIndices.map();

        shapeGeometry.map();
        shapePositions.map();
        shapeRotations.map();
        shapePrevPositions.map();
        shapePrevRotations.map();
        shapeFlags.map();

        shapeMatchingOffsets.map();
        shapeMatchingIndices.map();
        shapeMatchingMeshSize.map();
        shapeMatchingCoefficients.map();
        shapeMatchingPlasticThresholds.map();
        shapeMatchingPlasticCreeps.map();
        shapeMatchingRotations.map();
        shapeMatchingTranslations.map();
        shapeMatchingLocalPositions.map();
        shapeMatchingLocalNormals.map();

        springIndices.map();
        springLengths.map();
        springStiffness.map();

        tetraIndices.map();
        tetraStress.map();
        tetraRestPoses.map();
        tetraMaterialIndices.map();
        tetraFiberDirections.map();

        rigidBodies.map();
        rigidShapes.map();
        rigidJoints.map();
        cableLinks.map();
        muscles.map();

        inflatableTriOffsets.map();
        inflatableTriCounts.map();
        inflatableVolumes.map();
        inflatableCoefficients.map();
        inflatablePressures.map();

        triangles.map();
        triangleNormals.map();
        triangleFeatures.map();
        uvs.map();

        rigidParticleAttachments.map();
    }

    void UnmapBuffers()
    {
        // particles
        positions.unmap();
        restPositions.unmap();
        velocities.unmap();
        phases.unmap();
        densities.unmap();
        anisotropy1.unmap();
        anisotropy2.unmap();
        anisotropy3.unmap();
        normals.unmap();
        diffusePositions.unmap();
        diffuseVelocities.unmap();
        diffuseCount.unmap();
        smoothPositions.unmap();
        activeIndices.unmap();

        // convexes
        shapeGeometry.unmap();
        shapePositions.unmap();
        shapeRotations.unmap();
        shapePrevPositions.unmap();
        shapePrevRotations.unmap();
        shapeFlags.unmap();

        // rigids
        shapeMatchingOffsets.unmap();
        shapeMatchingIndices.unmap();
        shapeMatchingMeshSize.unmap();
        shapeMatchingCoefficients.unmap();
        shapeMatchingPlasticThresholds.unmap();
        shapeMatchingPlasticCreeps.unmap();
        shapeMatchingRotations.unmap();
        shapeMatchingTranslations.unmap();
        shapeMatchingLocalPositions.unmap();
        shapeMatchingLocalNormals.unmap();

        // springs
        springIndices.unmap();
        springLengths.unmap();
        springStiffness.unmap();

        // tetra
        tetraIndices.unmap();
        tetraStress.unmap();
        tetraRestPoses.unmap();
        tetraMaterialIndices.unmap();
        tetraFiberDirections.unmap();

        // rigids
        rigidBodies.unmap();
        rigidShapes.unmap();
        rigidJoints.unmap();
        cableLinks.unmap();
        muscles.unmap();

        // inflatables
        inflatableTriOffsets.unmap();
        inflatableTriCounts.unmap();
        inflatableVolumes.unmap();
        inflatableCoefficients.unmap();
        inflatablePressures.unmap();

        // triangles
        triangles.unmap();
        triangleNormals.unmap();
        triangleFeatures.unmap();
        uvs.unmap();

        rigidParticleAttachments.unmap();
    }
};


struct FlexContext
{
    NvFlexLibrary* flexLib = nullptr;

    NvFlexSolver* solver = nullptr;
    NvFlexSolverDesc desc;

    FlexBuffers* buffers = nullptr;

    NvFlexParams params;

    std::vector<FlexSoftBody> instances;
    std::vector<FlexRigidBody> rigids;

    glm::vec4 planes[8];
    int numPlanes = 0;

    pxr::UsdStageRefPtr stage;
    long int stageId;
    pxr::UsdPrim scene;

    carb::interop::Interop* interop;
    carb::interop::InteropContext* interopContext;

    // sharedparticle buffers
    carb::interop::InteropBuffer* interopParticleBuffer;
    carb::interop::InteropBuffer* interopNormalBuffer;

    typedef std::vector<std::string> AddedPrimQueue;
    typedef std::vector<std::string> RemovedPrimQueue;

    AddedPrimQueue addedPrims;
    RemovedPrimQueue removedPrims;

    int numNormals = 0;

    void init()
    {
        // acquire interop
        interop = carb::getFramework()->acquireInterface<carb::interop::Interop>();
        interopContext = interop->registerDeviceCPU();

        NvFlexInitDesc desc;
        desc.deviceIndex = 0;
        desc.enableExtensions = false;
        desc.renderDevice = nullptr;
        desc.renderContext = nullptr;
        desc.computeContext = nullptr;
        desc.runOnRenderContext = false;
        desc.computeType = eNvFlexCUDA;

        // initialize flex library
        flexLib = NvFlexInit(NV_FLEX_VERSION, &FlexErrorCallback, &desc);
        if (!flexLib)
        {
            CARB_LOG_ERROR("Failed to initialize Flex library");
            return;
        }

        // get loaded flex version
        int ver = NvFlexGetVersion();
        CARB_LOG_INFO("Loaded Flex version %d (%d.%d)", ver, ver / 100, ver % 100);

        buffers = new FlexBuffers(flexLib);
    }

    void destroy()
    {
        if (flexLib)
        {
            delete buffers;
            buffers = nullptr;

            NvFlexShutdown(flexLib);
            flexLib = nullptr;

            interop->unregisterContext(interopContext);
        }
    }

    void queueAdded(const char* path)
    {
        addedPrims.push_back(path);
    }

    void queueRemoved(const char* path)
    {
        removedPrims.push_back(path);
    }

    void processQueue()
    {
        for (auto path : addedPrims)
        {
            pxr::UsdPrim prim = stage->GetPrimAtPath(pxr::SdfPath(path.c_str()));

            ParsePrim(stageId, prim, this);
        }
    }


    void updateRender()
    {

#if USE_INTEROP

        glm::vec3* interopParticles = nullptr;
        glm::vec3* interopNormals = nullptr;

        if (buffers->positions.size())
            interop->mapWrite(nullptr, interopParticleBuffer, (void**)&interopParticles);

        if (buffers->normals.size())
            interop->mapWrite(nullptr, interopNormalBuffer, (void**)&interopNormals);

#endif // USE_INTEROP

        // sync soft USD instances
        for (size_t i = 0; i < instances.size(); ++i)
        {
            FlexSoftBody& inst = instances[i];

            UpdateAttachments(inst.attachments, inst.attachmentsEnabled, &buffers->positions[inst.particleOffset],
                              inst.particleCount);

            pxr::VtArray<pxr::GfVec3f> points;
            pxr::VtArray<pxr::GfVec3f> normals;

            points.resize(inst.particleCount);
#if !NON_SMOOTH_NORMAL_HACK
            normals.resize(inst.particleCount);
#else
            pxr::VtArray<int> renderVertexIndices;
            inst.simGeo.GetFaceVertexIndicesAttr().Get(&renderVertexIndices);
            normals.resize(renderVertexIndices.size());
#endif // NON_SMOOTH_NORMAL_HACK

            // transform particles from world space back to prim local space
            pxr::UsdGeomXform xform(inst.simGeo);
            pxr::GfMatrix4f worldToLocal =
                pxr::GfMatrix4f(xform.ComputeLocalToWorldTransform(pxr::UsdTimeCode::Default()).GetInverse());

            // read particles
            for (int i = 0; i < inst.particleCount; ++i)
            {
                const glm::vec4& p = buffers->positions[i + inst.particleOffset];
                points[i] = worldToLocal.Transform(pxr::GfVec3f(p.x, p.y, p.z));
#if !NON_SMOOTH_NORMAL_HACK
                const glm::vec3& n = buffers->normals[i + inst.particleOffset];
                normals[i] = worldToLocal.TransformDir(pxr::GfVec3f(n.x, n.y, n.z));
#endif // NON_SMOOTH_NORMAL_HACK
            }
#if NON_SMOOTH_NORMAL_HACK
            for (size_t i = 0; i < renderVertexIndices.size(); i++)
            {
                int vtxIndex = renderVertexIndices[i];
                const glm::vec3& n = buffers->normals[vtxIndex + inst.particleOffset];
                normals[i] = worldToLocal.TransformDir(pxr::GfVec3f(n.x, n.y, n.z));
            }
#endif // NON_SMOOTH_NORMAL_HACK

#if USE_INTEROP
            memcpy(&interopParticles[inst.particleOffset], &points[0], sizeof(pxr::GfVec3f) * inst.particleCount);
#    if !NON_SMOOTH_NORMAL_HACK
            memcpy(&interopNormals[inst.particleOffset], &normals[0], sizeof(pxr::GfVec3f) * inst.particleCount);
#    else
            memcpy(&interopNormals[inst.triangleOffset * 3], &normals[0], sizeof(pxr::GfVec3f) * normals.size());
#    endif

            if (iFastCache)
            {
                const char* primPath = inst.renderGeo.GetPath().GetText();

                carb::fastcache::BufferDesc pointDesc(&interopParticles[inst.particleOffset],
                                                      (uint32_t)sizeof(pxr::GfVec3f), (uint32_t)sizeof(pxr::GfVec3f));

                iFastCache->setPositionBuffer(primPath, pointDesc);

                carb::fastcache::BufferDesc normalDesc(&interopNormals[inst.triangleOffset * 3],
                                                       (uint32_t)sizeof(pxr::GfVec3f), (uint32_t)sizeof(pxr::GfVec3f));

                iFastCache->setNormalBuffer(primPath, normalDesc);
            }

#else
            // In the current state of this code, the "updateToUsd" and "useFastCache" settings are ignored.
            // That is, we are only writing to USD using slow updates for now.
            // In the future, we should probably fold interop support into the case where "useFastCache" is enabled
            // and "updateToUsd" is disabled.

            inst.renderGeo.GetPointsAttr().Set(points);
            inst.renderGeo.GetNormalsAttr().Set(normals);

            if (inst.tetraCount)
            {
                bool stressMaterialPresent = false;

                // optionally update color (texcoords based on stress), check if stress material assigned
                pxr::UsdRelationship rel = pxr::UsdShadeMaterial::GetBindingRel(inst.simGeo.GetPrim());
                if (rel)
                {
                    pxr::SdfPathVector paths;
                    rel.GetTargets(&paths);

                    for (size_t i = 0; i < paths.size(); ++i)
                    {
                        if (paths[i].GetName() == "stress")
                        {
                            stressMaterialPresent = true;
                            break;
                        }
                    }
                }

                if (stressMaterialPresent)
                {
                    std::vector<glm::vec2> averageStress(points.size(), glm::vec2(0.0f, 0.0f));

                    // calculate average Von-Mises stress on each vertex for visualization
                    const int tetraBegin = inst.tetraOffset;
                    const int tetraEnd = inst.tetraOffset + inst.tetraCount;

                    for (int i = tetraBegin; i < tetraEnd; ++i)
                    {
                        float s = fabsf(buffers->tetraStress[i]);

                        averageStress[buffers->tetraIndices[i * 4 + 0] - inst.particleOffset] += glm::vec2(s, 1.0f);
                        averageStress[buffers->tetraIndices[i * 4 + 1] - inst.particleOffset] += glm::vec2(s, 1.0f);
                        averageStress[buffers->tetraIndices[i * 4 + 2] - inst.particleOffset] += glm::vec2(s, 1.0f);
                        averageStress[buffers->tetraIndices[i * 4 + 3] - inst.particleOffset] += glm::vec2(s, 1.0f);
                    }

                    pxr::VtArray<pxr::GfVec2f> colors(points.size());

                    for (size_t i = 0; i < points.size(); ++i)
                    {
                        colors[i] = pxr::GfVec2f(averageStress[i].x / averageStress[i].y, 0.0f); // c[0], c[1]);//,
                                                                                                 // c[2]);
                    }

                    if (pxr::UsdGeomPrimvar var = inst.simGeo.CreatePrimvar(
                            pxr::TfToken("st"), pxr::SdfValueTypeNames->TexCoord2fArray, pxr::TfToken("vertex")))
                    {
                        if (!var.Set(colors))
                        {
                            CARB_LOG_WARN("Could not set FEM stress vertex colors");
                        }
                    }
                }
            }
#endif
        }
#if USE_INTEROP

        if (interopParticles)
            interop->unmapWrite(nullptr, interopParticleBuffer);

        if (interopNormals)
            interop->unmapWrite(nullptr, interopNormalBuffer);

#endif // USE_INTEROP
    }

    void simulate(float dt, int numSubsteps)
    {
        if (buffers->positions.size() == 0 && buffers->rigidBodies.size() == 0)
            return;

        // graphene uses variable update rate
        dt = std::min(1.0f / 60.0f, dt);

        for (size_t i = 0; i < rigids.size(); ++i)
        {
            FlexRigidBody& rigid = rigids[i];

            if (buffers->rigidBodies[rigid.rigidIndex].mass == 0.f)
            {
                pxr::GfVec3f pos;
                pxr::GfQuatf rot;
                pxr::GfVec3f scale;

                GetWorldTransform(rigid.xform, pos, rot, scale);

                // static / kinematic bodies sync their velocity to achieve desired USD xform over the course of the
                // frame
                NvFlexRigidPose pose = NvFlexMakeRigidPose((float*)&pos, (float*)&rot);
                NvFlexSetRigidTarget(&buffers->rigidBodies[rigid.rigidIndex], &pose, dt);
            }
        }

        buffers->UnmapBuffers();

        // update particle data
        NvFlexSetParticles(solver, buffers->positions.buffer, nullptr);
        NvFlexSetRestParticles(solver, buffers->restPositions.buffer, nullptr); // todo: do this only when necessary?
        NvFlexSetVelocities(solver, buffers->velocities.buffer, nullptr);
        NvFlexSetPhases(solver, buffers->phases.buffer, nullptr);
        NvFlexSetActive(solver, buffers->activeIndices.buffer, nullptr);
        NvFlexSetActiveCount(solver, buffers->activeIndices.size());

        // springs
        if (buffers->springIndices.size())
        {
            assert((buffers->springIndices.size() & 1) == 0);
            assert((buffers->springIndices.size() / 2) == buffers->springLengths.size());

            NvFlexSetSprings(solver, buffers->springIndices.buffer, buffers->springLengths.buffer,
                             buffers->springStiffness.buffer, buffers->springLengths.size());
        }

        // attachments
        if (buffers->rigidParticleAttachments.size())
        {
            NvFlexSetRigidParticleAttachments(
                solver, buffers->rigidParticleAttachments.buffer, buffers->rigidParticleAttachments.size());
        }

        if (buffers->triangles.size())
        {
            NvFlexSetDynamicTriangles(solver, buffers->triangles.buffer, buffers->triangleNormals.buffer, NULL,
                                      buffers->triangles.size() / 3);
        }

        if (buffers->tetraIndices.size())
        {
            NvFlexSetFEMGeometry(solver, buffers->tetraIndices.buffer, buffers->tetraRestPoses.buffer,
                                 buffers->tetraMaterialIndices.buffer, buffers->tetraFiberDirections.buffer,
                                 buffers->tetraMaterialIndices.size());
        }

        if (buffers->tetraMaterials.size())
        {
            NvFlexSetFEMMaterials(solver, &buffers->tetraMaterials[0], buffers->tetraMaterials.size());
        }


        if (buffers->inflatableTriOffsets.size())
            NvFlexSetInflatables(solver, buffers->inflatableTriOffsets.buffer, buffers->inflatableTriCounts.buffer,
                                 buffers->inflatableVolumes.buffer, buffers->inflatablePressures.buffer,
                                 buffers->inflatableCoefficients.buffer, int(buffers->inflatableTriCounts.size()));
        else
            NvFlexSetInflatables(solver, NULL, NULL, NULL, NULL, NULL, 0);


        // shape matching
        if (buffers->shapeMatchingOffsets.size())
        {
            NvFlexSetRigids(solver, buffers->shapeMatchingOffsets.buffer, buffers->shapeMatchingIndices.buffer,
                            buffers->shapeMatchingLocalPositions.buffer, buffers->shapeMatchingLocalNormals.buffer,
                            buffers->shapeMatchingCoefficients.buffer, buffers->shapeMatchingPlasticThresholds.buffer,
                            buffers->shapeMatchingPlasticCreeps.buffer, buffers->shapeMatchingRotations.buffer,
                            buffers->shapeMatchingTranslations.buffer, buffers->shapeMatchingOffsets.size() - 1,
                            buffers->shapeMatchingIndices.size());
        }

        // rigid bodies
        if (buffers->rigidBodies.size())
        {
            NvFlexSetRigidBodies(solver, buffers->rigidBodies.buffer, buffers->rigidBodies.size());
        }
        else
        {
            NvFlexSetRigidBodies(solver, nullptr, 0);
        }

        // rigid shapes
        if (buffers->rigidShapes.size())
        {
            NvFlexSetRigidShapes(solver, buffers->rigidShapes.buffer, buffers->rigidShapes.size());
        }
        else
        {
            NvFlexSetRigidShapes(solver, nullptr, 0);
        }

        // update joints
        if (buffers->rigidJoints.size())
        {
            NvFlexSetRigidJoints(solver, buffers->rigidJoints.buffer, buffers->rigidJoints.size());
        }
        else
        {
            NvFlexSetRigidJoints(solver, nullptr, 0);
        }

        if (buffers->shapeFlags.size())
        {
            // legacy collision shapes
            NvFlexSetShapes(solver, buffers->shapeGeometry.buffer, buffers->shapePositions.buffer,
                            buffers->shapeRotations.buffer, buffers->shapePrevPositions.buffer,
                            buffers->shapePrevRotations.buffer, buffers->shapeFlags.buffer,
                            int(buffers->shapeFlags.size()));
        }

        // simulate
        NvFlexSetParams(solver, &params);
        NvFlexUpdateSolver(solver, dt, numSubsteps, false);

        // launch read back
        NvFlexGetParticles(solver, buffers->positions.buffer, nullptr);
        NvFlexGetVelocities(solver, buffers->velocities.buffer, nullptr);
        NvFlexGetNormals(solver, buffers->normals.buffer, nullptr);

        // readback triangle normals
        if (buffers->triangles.size())
        {
            NvFlexGetDynamicTriangles(solver, buffers->triangles.buffer, buffers->triangleNormals.buffer, nullptr,
                                      buffers->triangles.size() / 3);
        }

        // readback rigid transforms
        if (buffers->shapeMatchingOffsets.size())
        {
            NvFlexGetRigids(solver, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                            buffers->shapeMatchingRotations.buffer, buffers->shapeMatchingTranslations.buffer);
        }

        // tetrahedral stress
        if (buffers->tetraStress.size())
        {
            NvFlexGetFEMStress(solver, buffers->tetraStress.buffer);
        }

        // rigid bodies
        if (buffers->rigidBodies.size())
        {
            NvFlexGetRigidBodies(solver, buffers->rigidBodies.buffer);
        }

        // cables
        if (buffers->cableLinks.size())
        {
            NvFlexGetCableLinks(solver, buffers->cableLinks.buffer);
        }

        // map buffers
        buffers->MapBuffers();

#if FLEX_PROFILE
        float latency = NvFlexGetDeviceLatency(solver, NULL, NULL, NULL);
        CARB_LOG_INFO("GPU time: %f\n", latency * 1000.0f);
#endif

        // clear forces
        for (int i = 0; i < buffers->rigidBodies.size(); ++i)
        {
            NvFlexRigidBody& body = buffers->rigidBodies[i];

            body.force[0] = 0.0f;
            body.force[1] = 0.0f;
            body.force[2] = 0.0f;

            body.torque[0] = 0.0f;
            body.torque[1] = 0.0f;
            body.torque[2] = 0.0f;
        }

        // sync rigid USD instances
        for (size_t i = 0; i < rigids.size(); ++i)
        {
            FlexRigidBody& rigid = rigids[i];

            if (buffers->rigidBodies[rigid.rigidIndex].mass == 0.f)
            {
                // static bodies sync their transform from USD->Flex
                pxr::GfVec3f pos;
                pxr::GfQuatf rot;
                pxr::GfVec3f scale;

                GetWorldTransform(rigid.xform, pos, rot, scale);

                NvFlexRigidPose pose = NvFlexMakeRigidPose((float*)&pos, (float*)&rot);
                NvFlexSetRigidPose(&buffers->rigidBodies[rigid.rigidIndex], &pose);
            }
            else
            {
                // dynamic bodies sync their transform from Flex->USD
                NvFlexRigidPose pose;
                NvFlexGetRigidPose(&buffers->rigidBodies[i], &pose);

                SetWorldTransform(rigid.xform, pxr::GfVec3f(pose.p[0], pose.p[1], pose.p[2]),
                                  pxr::GfQuatf(pose.q[3], pose.q[0], pose.q[1], pose.q[2]));
            }
        }

        updateRender();
    }
}; // struct FlexContext

FlexContext* g_flexContext = nullptr;
omni::kit::IStageUpdate* g_stageUpdate = nullptr;
omni::kit::StageUpdateNode* g_stageUpdateNode = nullptr;

void ParseMaterial(const pxr::UsdPrim& prim, NvFlexRigidMaterial* material, float* thickness, float* density)
{
    if (prim)
    {
        ReadAttribute(prim, "staticFriction", &material->friction);
        ReadAttribute(prim, "torsionFriction", &material->torsionFriction);
        ReadAttribute(prim, "rollingFriction", &material->rollingFriction);
        ReadAttribute(prim, "restitution", &material->restitution);
        ReadAttribute(prim, "compliance", &material->compliance);

        ReadAttribute(prim, "thickness", thickness);
        ReadAttribute(prim, "density", density);
    }
    else
    {
        material->friction = 0.5f;
        material->compliance = 0.0f;
        material->restitution = 0.0f;
        material->torsionFriction = 0.0f;
        material->rollingFriction = 0.0f;

        *thickness = 0.01f;
        *density = 1.0f;
    }
}

bool ParseShape(const pxr::UsdPrim& shapePrim,
                const pxr::UsdPrim& bodyPrim,
                int bodyIndex,
                NvFlexRigidShape* shape,
                glm::vec4* planes,
                int* numPlanes)
{
    pxr::GfMatrix4d shapePose = GetWorldTransform(shapePrim);
    pxr::GfMatrix4d bodyPose = GetWorldTransform(bodyPrim);

    // shape pose relative to body
    pxr::GfMatrix4d localPose = bodyPose.GetInverse() * shapePose;

    pxr::GfVec3f pos = pxr::GfVec3f(localPose.ExtractTranslation());
    pxr::GfQuatf rot = pxr::GfQuatf(localPose.ExtractRotation().GetQuat());
    pxr::GfVec3f scale = pxr::GfVec3f(pxr::GfTransform(shapePose).GetScale());

    NvFlexRigidPose pose = NvFlexMakeRigidPose(&pos[0], (float*)&rot);

    if (shapePrim.IsA<pxr::UsdGeomCube>())
    {
        NvFlexMakeRigidBoxShape(shape, bodyIndex, scale[0], scale[1], scale[2], pose);

        // to account for cm
        shape->thickness *= 100.0f;
    }
    else if (shapePrim.GetTypeName() == pxr::TfToken("Plane"))
    {
        pxr::GfVec4f xyzw;
        if (ReadAttribute(shapePrim, "xyzw", &xyzw))
        {
            // compatability with old assets, let users specify plane equation directly
            planes[*numPlanes][0] = xyzw[0];
            planes[*numPlanes][1] = xyzw[1];
            planes[*numPlanes][2] = xyzw[2];
            planes[*numPlanes][3] = xyzw[3];
        }
        else
        {
            pxr::GfVec3f p;
            pxr::GfQuatf q;
            pxr::GfVec3f s;

            GetWorldTransform(shapePrim, p, q, s);

            // default to z-axis
            int planeAxis = 2;

            pxr::TfToken axis;
            ReadAttribute(shapePrim, "axis", &axis);

            if (axis == pxr::TfToken("X"))
            {
                planeAxis = 0;
            }
            else if (axis == pxr::TfToken("Y"))
            {
                planeAxis = 1;
            }
            else if (axis == pxr::TfToken("Z"))
            {
                planeAxis = 2;
            }

            pxr::GfVec3f normal(0.0f);
            normal[planeAxis] = 1.0f;

            pxr::GfVec3f y = pxr::GfRotation(q).TransformDir(normal);

            planes[*numPlanes][0] = y[0];
            planes[*numPlanes][1] = y[1];
            planes[*numPlanes][2] = y[2];
            planes[*numPlanes][3] = -pxr::GfDot(y, p);
        }

        (*numPlanes)++;
        return false; // return false since planes are not handled as a shape
    }
    else if (shapePrim.IsA<pxr::UsdGeomSphere>())
    {
        // must be double or will not read attr correctly
        double radius = 1.0f;
        ReadAttribute(shapePrim, "radius", &radius);

        // assume uniform scale
        radius *= scale[0];

        NvFlexMakeRigidSphereShape(shape, bodyIndex, float(radius), pose);
    }
    else if (shapePrim.IsA<pxr::UsdGeomCapsule>())
    {
        // must be double or will not read attr correctly
        double height = 1.0f;
        double radius = 0.5f;

        ReadAttribute(shapePrim, "height", &height);
        ReadAttribute(shapePrim, "radius", &radius);

        // todo: capsule also has an axis attribute to change orientation, default is along Z
        height *= scale[2];
        radius *= scale[0];

        // rotate shape so that x-axis is along z-axis
        rot = pxr::GfQuatf(rot * pxr::GfRotation(pxr::GfVec3d(0.0, 1.0f, 0.0f), 90.0).GetQuat());

        // update pose
        pose = NvFlexMakeRigidPose(&pos[0], (float*)&rot);

        NvFlexMakeRigidCapsuleShape(shape, bodyIndex, float(radius), float(height * 0.5f), pose);
    }
    else if (shapePrim.IsA<pxr::UsdGeomMesh>())
    {
        NvFlexTriangleMeshId meshId = MakeRigidTriangleMesh(g_flexContext->flexLib, shapePrim);
        NvFlexMakeRigidTriangleMeshShape(shape, bodyIndex, meshId, pose, scale[0], scale[1], scale[2]);
    }
    else
    {
        CARB_LOG_WARN("Could not convert USD shapePrim to Flex collision shape");
        return false;
    }

    ReadAttribute(shapePrim, "filter", &shape->filter);
    ReadAttribute(shapePrim, "group", &shape->group);
    shape->filter = 0;

    return true;
}

void ParseCollision(const pxr::UsdPrim& shapePrim,
                    const pxr::UsdPrim& bodyPrim,
                    std::vector<NvFlexRigidShape>& shapes,
                    std::vector<float>& densities,
                    glm::vec4* planes,
                    int* numPlanes,
                    int rigidIndex)
{
    bool collisionEnabled = true;
    ReadAttribute(shapePrim, "collisionEnabled", &collisionEnabled);

    if (collisionEnabled)
    {
        NvFlexRigidMaterial mat;
        float thickness, density;
        ParseMaterial(GetRelPrim(shapePrim, "physicsMaterial"), &mat, &thickness, &density);

        NvFlexRigidShape shape;
        if (ParseShape(shapePrim, bodyPrim, rigidIndex, &shape, planes, numPlanes))
        {
            if (rigidIndex == -1)
            {
                // no parent body, treat as static collider in world space
                pxr::GfVec3f pos;
                pxr::GfQuatf rot;
                pxr::GfVec3f scale;
                GetWorldTransform(shapePrim, pos, rot, scale);

                shape.pose = NvFlexMakeRigidPose((float*)&pos, (float*)&rot);
            }

            // check if per-shape density (overrides material density)
            float shapeDensity = density;
            ReadAttribute(shapePrim, "density", &shapeDensity);

            // allow shape to override thickness (schema extension)
            float shapeThickness = thickness;
            ReadAttribute(shapePrim, "thickness", &shapeThickness);

            shape.material = mat;
            shape.thickness = shapeThickness;

            shapes.push_back(shape);
            densities.push_back(shapeDensity);
        }
    }
}

// reads a SoftBodyMaterial prim and either creates or updates the
// materials array with the material returns the index to the new material
int ParseSoftMaterial(pxr::UsdPrim prim, std::vector<NvFlexFEMMaterial>& materials)
{
    if (!prim)
    {
        CARB_LOG_WARN("Could not find referenced SoftMaterial: %s", prim.GetPath().GetString().c_str());

        // add default material
        float poisson = 0.45;

        NvFlexFEMMaterial mat = IsotropicMaterial(eNvFlexFEMModelCorotational, poisson, 0.0f);

        int index = materials.size();
        materials.push_back(mat);

        return index;
    }

    int materialIndex = -1;

    float youngs = 1.e+5f;
    float poisson = 0.45f;
    float activation = 0.0f;
    float activationMax = 1.e+5f;
    pxr::TfToken model("corotational");

    ReadAttribute(prim, "model", &model);
    ReadAttribute(prim, "youngsModulus", &youngs, 0.0f, FLT_MAX);
    ReadAttribute(prim, "poissonsRatio", &poisson, -0.49f, 0.49f);
    ReadAttribute(prim, "fiberActivation", &activation, 0.0f, 1.0f);
    ReadAttribute(prim, "fiberStiffness", &activationMax, 0.0f, FLT_MAX);

    NvFlexFEMMaterial material;

    if (model == pxr::TfToken("hyperelastic"))
    {
        material = IsotropicMaterial(eNvFlexFEMModelNeoHookean, youngs, poisson, 0.0f);
    }
    else
    {
        material = IsotropicMaterial(eNvFlexFEMModelCorotational, youngs, poisson, 0.0f);
    }

    material.activation = activation;
    material.activationMax = activationMax;

    // Flex material index stored in the prim custom data section
    const pxr::TfToken matToken("materialIndex");

    if (prim.HasCustomDataKey(matToken))
    {
        materialIndex = prim.GetCustomDataByKey(matToken).Get<int>();

        if (materialIndex >= 0 && (size_t)materialIndex < materials.size())
        {
            // update existing material
            materials[materialIndex] = material;
            return materialIndex;
        }
        else
        {
            CARB_LOG_ERROR("Stored material index was outside of valid range, index: %d material size: %d",
                           materialIndex, int(materials.size()));
        }
    }

    // allocate a new material and set on the material prim
    materialIndex = materials.size();
    materials.push_back(material);

    prim.SetCustomDataByKey(matToken, pxr::VtValue(materialIndex));

    return materialIndex;
}

// Helper to get value
template <typename TValue>
TValue getUSDValue(const pxr::UsdAttribute& attribute)
{
    TValue value = TValue();
    if (attribute)
    {
        std::vector<double> times;
        attribute.GetTimeSamples(&times);

        attribute.Get(&value, times.size() > 0 ? times[0] : pxr::UsdTimeCode::Default());
    }

    return value;
}

void parseSoftBodyPrim(const pxr::UsdPrim& prim,
                       const pxr::UsdPrim& mesh,
                       const pxr::UsdPrim& renderMesh,
                       FlexContext* context)
{
    FlexBuffers* buffers = context->buffers;

    float stretchStiffness = 1.0;
    float bendStiffness = 0.5f;
    float pressure = 0.0f;
    int group = 0;
    pxr::GfVec3f initialVelocity = pxr::GfVec3f(0.0f);
    float initialVelocityRand = 0.0f;

    ReadAttribute(prim, "stretchStiffness", &stretchStiffness);
    ReadAttribute(prim, "bendStiffness", &bendStiffness);
    ReadAttribute(prim, "pressure", &pressure, 0.1f, 6.0f);
    ReadAttribute(prim, "collisionGroup", &group);
    ReadAttribute(prim, "initialVelocity", &initialVelocity);
    ReadAttribute(prim, "initialVelocityRand", &initialVelocityRand);

    pxr::UsdGeomMesh geo(mesh);
    pxr::UsdGeomMesh renderGeo(renderMesh);

    // get geometry transform
    pxr::UsdGeomXform xform(geo);
    pxr::GfMatrix4d localToWorld = xform.ComputeLocalToWorldTransform(pxr::UsdTimeCode::Default());

    pxr::VtArray<pxr::GfVec3f> points;
    pxr::VtArray<int> vertexCounts;
    pxr::VtArray<int> vertexIndices;
    pxr::VtArray<float> mass;

    pxr::VtArray<int> springIndices;
    pxr::VtArray<float> springLengths;
    pxr::VtArray<float> springCoefficients;

    pxr::VtArray<int> tetraIndices;
    pxr::VtArray<int> tetraMaterialIndices;
    pxr::VtArray<pxr::GfVec4f> tetraFiberDirections;
    pxr::VtArray<pxr::GfMatrix3f> tetraRestPoses;

    pxr::VtArray<int> triIndices;

    geo.GetPointsAttr().Get(&points);
    geo.GetFaceVertexCountsAttr().Get(&vertexCounts);
    geo.GetFaceVertexIndicesAttr().Get(&vertexIndices);

    pxr::VtArray<int> faceVertexIndices;
    geo.GetFaceVertexIndicesAttr().Get(&faceVertexIndices);

    // optional constraint arrays, these may be created dynamically in the next phase if a generator
    // string is set
    ReadAttribute(mesh, "springIndices", &springIndices);
    ReadAttribute(mesh, "springRestLengths", &springLengths);
    ReadAttribute(mesh, "springCoefficients", &springCoefficients);

    ReadAttribute(mesh, "tetraIndices", &tetraIndices);
    ReadAttribute(mesh, "tetraMaterialIndices", &tetraMaterialIndices);
    ReadAttribute(mesh, "tetraFiberDirections", &tetraFiberDirections);

    ReadAttribute(mesh, "faceVertexIndices", &triIndices);

    // todo: how can we serialize rest poses? Looks like we can't put GfMatrix3f into a UsdAttribute
    // (not a value type), just flatten to float? for now we will recompute them on load
    // ReadAttribute(mesh, "tetraRestPoses", &tetraRestPoses);

    // read mass from file
    float massScale = 1.0f;
    ReadAttribute(mesh, "massScale", &massScale);

    if (pxr::UsdAttribute attr = geo.GetPrim().GetAttribute(pxr::TfToken("mass")))
    {
        attr.Get(&mass);
    }
    else
    {
        // default mass
        mass.resize(points.size());

        for (size_t i = 0; i < points.size(); ++i)
        {
            mass[i] = 1.0f;
        }
    }

    // apply mass scale
    for (size_t i = 0; i < mass.size(); ++i)
    {
        mass[i] *= massScale;
    }

    // build particles with inv mass
    std::vector<glm::vec4> particles(points.size());

    for (size_t i = 0; i < points.size(); ++i)
    {
        pxr::GfVec3f p = localToWorld.Transform(points[i]);

        particles[i].x = p[0];
        particles[i].y = p[1];
        particles[i].z = p[2];

        if (mass[i] > 0.0f)
        {
            particles[i].w = 1.0f / mass[i];
        }
        else
        {
            particles[i].w = 0.0f;
        }
    }

    // default to building a surface cloth constraint network
    std::string mode = "cloth";
    ReadAttribute(mesh, "generator", &mode);

    // default dir for muscle actuations
    pxr::GfVec3f fiberDir = pxr::GfVec3f(1.0f, 0.0f, 0.0f);
    ReadAttribute(mesh, "fiberDir", &fiberDir);

    NvFlexExtAsset* asset = NULL;

    if (mode == "cloth")
    {
        asset =
            NvFlexExtCreateClothFromMesh(&particles[0].x, particles.size(), &vertexIndices[0], vertexIndices.size() / 3,
                                         stretchStiffness, bendStiffness, 0.0f, 0.0f, pressure);
    }
    else if (mode == "clothgrid")
    {
    }
    else if (mode == "tetgrid")
    {
        int dimx = 0;
        int dimy = 0;
        int dimz = 0;
        float cellWidth = 0.0f;
        float cellHeight = 0.0f;
        float cellDepth = 0.0f;
        float density = 1000.0f;

        ReadAttribute(mesh, "dimx", &dimx);
        ReadAttribute(mesh, "dimy", &dimy);
        ReadAttribute(mesh, "dimz", &dimz);

        ReadAttribute(mesh, "cellWidth", &cellWidth);
        ReadAttribute(mesh, "cellHeight", &cellHeight);
        ReadAttribute(mesh, "cellDepth", &cellDepth);

        ReadAttribute(mesh, "density", &density);

        // -x, +x, -y, +y, -z, +z
        bool fixedEdges[6] = { false, false, false, false, false, false };

        ReadAttribute(mesh, "fixNegativeX", &fixedEdges[0]);
        ReadAttribute(mesh, "fixPositiveX", &fixedEdges[1]);
        ReadAttribute(mesh, "fixNegativeY", &fixedEdges[2]);
        ReadAttribute(mesh, "fixPositiveY", &fixedEdges[3]);
        ReadAttribute(mesh, "fixNegativeZ", &fixedEdges[4]);
        ReadAttribute(mesh, "fixPositiveZ", &fixedEdges[5]);

        asset = NvFlexExtCreateTetraGrid(dimx, dimy, dimz, cellWidth, cellHeight, cellDepth, density, 0, fixedEdges[2],
                                         fixedEdges[3], fixedEdges[0], fixedEdges[1]);

        // update USD geometry with initial grid mesh
        points.resize(asset->numParticles);
        vertexCounts.resize(asset->numTriangles);
        vertexIndices.resize(asset->numTriangles * 3);

        for (int i = 0; i < asset->numParticles; ++i)
        {
            pxr::GfVec3f p =
                pxr::GfVec3f(asset->particles[i * 4 + 0], asset->particles[i * 4 + 1], asset->particles[i * 4 + 2]);

            points[i] = p;
        }

        for (int i = 0; i < asset->numTriangles; ++i)
        {
            vertexCounts[i] = 3;
            vertexIndices[i * 3 + 0] = asset->triangleIndices[i * 3 + 0];
            vertexIndices[i * 3 + 1] = asset->triangleIndices[i * 3 + 1];
            vertexIndices[i * 3 + 2] = asset->triangleIndices[i * 3 + 2];
        }

        if (renderMesh.IsValid())
        {
            renderGeo.GetPointsAttr().Set(points);
            renderGeo.GetFaceVertexCountsAttr().Set(vertexCounts);
            renderGeo.GetFaceVertexIndicesAttr().Set(vertexIndices);
        }
        else
        {
            geo.GetPointsAttr().Set(points);
            geo.GetFaceVertexCountsAttr().Set(vertexCounts);
            geo.GetFaceVertexIndicesAttr().Set(vertexIndices);
        }

        for (int i = 0; i < asset->numParticles; ++i)
        {
            // apply localToWorld transform (todo: if scale is present need to update tetraRestPose as
            // well)
            pxr::GfVec3f& p = (pxr::GfVec3f&)asset->particles[i * 4];
            p = localToWorld.Transform(p);
        }
    }
    else if (mode == "tetgen")
    {
    }
    else if (mode == "custom")
    {
        // if rest poses not filled then compute them now
        if (tetraIndices.size() && tetraRestPoses.empty())
        {
            const int numTetra = tetraIndices.size() / 4;
            tetraRestPoses.resize(numTetra);

            for (int t = 0; t < numTetra; ++t)
            {
                int i = tetraIndices[t * 4 + 0];
                int j = tetraIndices[t * 4 + 1];
                int k = tetraIndices[t * 4 + 2];
                int l = tetraIndices[t * 4 + 3];

                glm::vec4 x0 = particles[i];
                glm::vec4 x1 = particles[j];
                glm::vec4 x2 = particles[k];
                glm::vec4 x3 = particles[l];

                x1 -= glm::vec4(glm::vec3(x0), 0.0f);
                x2 -= glm::vec4(glm::vec3(x0), 0.0f);
                x3 -= glm::vec4(glm::vec3(x0), 0.0f);

                glm::mat3 Q = glm::mat3(glm::vec3(x1), glm::vec3(x2), glm::vec3(x3));
                glm::mat3 rest = glm::inverse(Q);

                const float det = glm::determinant(Q);

                if (fabsf(det) <= 1.e-9f)
                {
                    CARB_LOG_WARN("Degenerate or inverted tet\n");
                }

                tetraRestPoses[t] = (pxr::GfMatrix3f&)rest;
            }
        }

        if (tetraIndices.size() && tetraMaterialIndices.empty())
        {
            // assign default material if not specified
            const int numTetra = tetraIndices.size() / 4;
            tetraMaterialIndices.resize(numTetra);

            for (int t = 0; t < numTetra; ++t)
            {
                tetraMaterialIndices[t] = 0;
            }
        }

        // construct a FlexAsset from the data directly
        asset = new NvFlexExtAsset();
        memset(asset, 0, sizeof(NvFlexExtAsset));

        asset->particles = (float*)particles.data();

        asset->springIndices = springIndices.data();
        asset->springRestLengths = springLengths.data();
        asset->springCoefficients = springCoefficients.data();

        asset->tetraIndices = tetraIndices.data();
        asset->tetraRestPoses = (float*)tetraRestPoses.data();
        asset->tetraMaterials = tetraMaterialIndices.data();

        asset->triangleIndices = triIndices.data();
        asset->numTriangles = triIndices.size() / 3;

        asset->numParticles = particles.size();
        asset->numSprings = springLengths.size();
        asset->numTetra = tetraRestPoses.size();
    }

    // create map from asset material indices to global material indices
    std::vector<int> materialLookup;

    if (asset->numTetra)
    {
        if (pxr::UsdRelationship rel = prim.GetRelationship(pxr::TfToken("dynamicsMaterials")))
        {
            pxr::SdfPathVector paths;
            if (rel.GetTargets(&paths))
            {
                for (size_t i = 0; i < paths.size(); ++i)
                {
                    pxr::UsdPrim materialPrim(context->stage->GetPrimAtPath(paths[i]));

                    int materialIndex = ParseSoftMaterial(materialPrim, buffers->tetraMaterials);
                    materialLookup.push_back(materialIndex);
                }
            }
        }
        else
        {
            float youngs = 1.e+5f;
            float poisson = 0.4;

            // create default unique material for this object
            NvFlexFEMMaterial mat = IsotropicMaterial(eNvFlexFEMModelCorotational, youngs, poisson, 0.0f);

            materialLookup.push_back(buffers->tetraMaterials.size());
            buffers->tetraMaterials.push_back(mat);
        }
    }

    if (asset)
    {
        // if fiber directions empty then set to default now
        if (asset->numTetra && tetraFiberDirections.empty())
        {
            tetraFiberDirections.resize(asset->numTetra);

            for (int t = 0; t < asset->numTetra; ++t)
            {
                tetraFiberDirections[t] = pxr::GfVec4f(fiberDir[0], fiberDir[1], fiberDir[2], 0.0f);
            }
        }

        FlexSoftBody instance;
        instance.softbody = prim;
        instance.simGeo = geo;
        instance.renderGeo = renderGeo;

        instance.particleOffset = int(buffers->positions.size());
        instance.particleCount = asset->numParticles;
        instance.triangleOffset = int(buffers->triangles.size() / 3);
        instance.triangleCount = asset->numTriangles;
        instance.tetraOffset = int(buffers->tetraIndices.size() / 4);
        instance.tetraCount = asset->numTetra;

        const int phase = NvFlexMakePhase(group, eNvFlexPhaseSelfCollide | eNvFlexPhaseSelfCollideFilter);

        for (int i = 0; i < asset->numParticles; ++i)
        {
            buffers->activeIndices.push_back(buffers->positions.size());

            glm::vec4 p(asset->particles[i * 4 + 0], asset->particles[i * 4 + 1], asset->particles[i * 4 + 2],
                        asset->particles[i * 4 + 3]);

            glm::vec3 v = glm::vec3(initialVelocity[0], initialVelocity[1], initialVelocity[2]);

            v.x += (float(rand()) / RAND_MAX * 2.0f - 1.0f) * initialVelocityRand;
            v.y += (float(rand()) / RAND_MAX * 2.0f - 1.0f) * initialVelocityRand;
            v.z += (float(rand()) / RAND_MAX * 2.0f - 1.0f) * initialVelocityRand;

            buffers->positions.push_back(p);
            buffers->restPositions.push_back(p);
            buffers->velocities.push_back(v);
            buffers->normals.push_back(glm::vec4(0.0f, 0.0f, 0.0f, 0.0f));
            buffers->phases.push_back(phase);
        }
#if NON_SMOOTH_NORMAL_HACK && USE_INTEROP
        context->numNormals += faceVertexIndices.size();
#endif // NON_SMOOTH_NORMAL_HACK
        for (int i = 0; i < asset->numTriangles; ++i)
        {
            buffers->triangles.push_back(asset->triangleIndices[i * 3 + 0] + instance.particleOffset);
            buffers->triangles.push_back(asset->triangleIndices[i * 3 + 1] + instance.particleOffset);
            buffers->triangles.push_back(asset->triangleIndices[i * 3 + 2] + instance.particleOffset);

            buffers->triangleNormals.push_back(glm::vec3(0.0f, 0.0f, 1.0f));
        }

        for (int i = 0; i < asset->numSprings; ++i)
        {
            buffers->springIndices.push_back(asset->springIndices[i * 2 + 0] + instance.particleOffset);
            buffers->springIndices.push_back(asset->springIndices[i * 2 + 1] + instance.particleOffset);
            buffers->springStiffness.push_back(asset->springCoefficients[i]);
            buffers->springLengths.push_back(asset->springRestLengths[i]);
        }

        if (pressure > 0.0f)
        {
            instance.inflatableOffset = buffers->inflatablePressures.size();

            buffers->inflatableTriOffsets.push_back(instance.triangleOffset);
            buffers->inflatableTriCounts.push_back(asset->numTriangles);
            buffers->inflatablePressures.push_back(pressure);
            buffers->inflatableVolumes.push_back(asset->inflatableVolume);
            buffers->inflatableCoefficients.push_back(asset->inflatableStiffness);
        }

        for (int i = 0; i < asset->numTetra; ++i)
        {
            buffers->tetraIndices.push_back(asset->tetraIndices[i * 4 + 0] + instance.particleOffset);
            buffers->tetraIndices.push_back(asset->tetraIndices[i * 4 + 1] + instance.particleOffset);
            buffers->tetraIndices.push_back(asset->tetraIndices[i * 4 + 2] + instance.particleOffset);
            buffers->tetraIndices.push_back(asset->tetraIndices[i * 4 + 3] + instance.particleOffset);

            buffers->tetraRestPoses.push_back(*(const glm::mat3*)&asset->tetraRestPoses[i * 9]);
            buffers->tetraFiberDirections.push_back((const glm::vec4&)tetraFiberDirections[i]);
            buffers->tetraMaterialIndices.push_back(materialLookup[asset->tetraMaterials[i]]);
            buffers->tetraStress.push_back(0.0f);
        }

        // create particle attachments
        float attachmentDistance = -1.0f;
        ReadAttribute(prim, "attachDistance", &attachmentDistance);
        ReadAttribute(prim, "attachEnabled", &instance.attachmentsEnabled);

        if (attachmentDistance >= 0.0f)
        {
            CreateAttachments(context->stage, &buffers->positions[instance.particleOffset], instance.particleCount,
                              attachmentDistance, instance.attachments);
        }

        // add instance to context
        g_flexContext->instances.push_back(instance);

        // custom mode doesn't go through Flex extensions
        if (mode == "custom")
            delete asset;
        else
            NvFlexExtDestroyAsset(asset);
    }
}

// returns true if subtree should be traversed, false otherwise
bool ParsePrim(long int stageId, const pxr::UsdPrim& prim, FlexContext* context)
{
    FlexBuffers* buffers = context->buffers;

    // for rigids we want to simulate in Flex use a custom attribute of 'bool FlexRigidAPI = true' and don't assign
    // PhysicsAPI
    if (HasSchema(prim, pxr::TfToken("PhysicsAPI")) || HasAttribute(prim, pxr::TfToken("FlexRigidAPI")))
    {
        const int rigidIndex = buffers->rigidBodies.size();

        bool physicsEnabled = false;
        ReadAttribute(prim, "physicsEnabled", &physicsEnabled);

        std::vector<NvFlexRigidShape> shapes;
        std::vector<float> densities;

        // traverse subtree using a separate iterator
        pxr::UsdPrimRange children = pxr::UsdPrimRange(prim);

        for (const pxr::UsdPrim& c : children)
        {
            if (HasSchema(c, pxr::TfToken("CollisionAPI")))
            {
                ParseCollision(c, prim, shapes, densities, context->planes, &context->numPlanes, rigidIndex);
            }
        }

        if (shapes.size())
        {
            FlexRigidBody rigid;
            rigid.rigidIndex = rigidIndex;
            rigid.xform = prim;
            rigid.rigidShapeOffset = buffers->rigidShapes.size();
            rigid.rigidShapeCount = shapes.size();

            context->rigids.push_back(rigid);

            // todo: read mass properties from file

            pxr::GfVec3f pos;
            pxr::GfQuatf rot;
            pxr::GfVec3f scale;
            GetWorldTransform(rigid.xform, pos, rot, scale);

            // add body
            NvFlexRigidBody body;
            NvFlexMakeRigidBody(
                context->flexLib, &body, (float*)&pos, (float*)&rot, &shapes[0], &densities[0], shapes.size());

            // use "FlexRigidAPI" as attribute for Flex only, if it's not present assume body is a PhysX body
            if (!physicsEnabled || !HasAttribute(prim, pxr::TfToken("FlexRigidAPI")))
            {
                body.mass = 0.0f;
                body.invMass = 0.0f;

                memset(body.inertia, 0, sizeof(body.inertia));
                memset(body.invInertia, 0, sizeof(body.invInertia));
            }

            // add bodies and shapes to Flex buffers
            buffers->rigidBodies.push_back(body);

            for (size_t i = 0; i < shapes.size(); ++i)
                buffers->rigidShapes.push_back(shapes[i]);
        }

        // skip rest of the subtree (don't allow nested physics bodies)
        return false;
    }
    else if (HasSchema(prim, pxr::TfToken("CollisionAPI")))
    {
        // non-parented collision shape, treat as a static body
        std::vector<NvFlexRigidShape> shapes;
        std::vector<float> densities;

        FlexRigidBody rigid;
        rigid.rigidIndex = buffers->rigidBodies.size();
        rigid.xform = prim;
        rigid.rigidShapeOffset = buffers->rigidShapes.size();
        rigid.rigidShapeCount = shapes.size();

        context->rigids.push_back(rigid);

        // identity root body
        pxr::GfVec3f pos;
        pxr::GfQuatf rot;
        pxr::GfVec3f scale;
        GetWorldTransform(rigid.xform, pos, rot, scale);

        NvFlexRigidBody body;
        NvFlexMakeRigidBody(
            context->flexLib, &body, (float*)&pos, (float*)&rot, shapes.data(), densities.data(), shapes.size());

        // add a dummy kinematic body for each static collider
        body.mass = 0.0f;
        body.invMass = 0.0f;

        memset(body.inertia, 0, sizeof(body.inertia));
        memset(body.invInertia, 0, sizeof(body.invInertia));

        // add bodies and shapes to Flex buffers
        buffers->rigidBodies.push_back(body);

        ParseCollision(prim, prim, shapes, densities, context->planes, &context->numPlanes, rigid.rigidIndex);

        for (size_t i = 0; i < shapes.size(); ++i)
            buffers->rigidShapes.push_back(shapes[i]);
    }
    else if (strcmp(prim.GetTypeName().GetText(), "SoftBody") == 0)
    {
        // If there is a proxyMesh relationship, then use the mesh specified by it
        // This is useful for handling triangulated mesh data
        // Note: the newly created triangulated data is stored in def Mesh "ProxyMesh"
        if (pxr::UsdRelationship rel = prim.GetRelationship(pxr::TfToken("proxyMesh")))
        {
            pxr::SdfPathVector paths;
            if (rel.GetTargets(&paths))
            {
                pxr::UsdPrim mesh(context->stage->GetPrimAtPath(paths[0]));
                if (!mesh)
                {
                    CARB_LOG_WARN("Could not find referenced proxyMesh: %s", paths[0].GetString().c_str());
                    return true;
                }

                // Get render mesh
                if (pxr::UsdRelationship renderRel = prim.GetRelationship(pxr::TfToken("dynamicsMesh")))
                {
                    pxr::SdfPathVector renderMeshPaths;
                    if (renderRel.GetTargets(&renderMeshPaths))
                    {
                        pxr::UsdPrim renderMesh(context->stage->GetPrimAtPath(renderMeshPaths[0]));
                        if (!renderMesh)
                        {
                            CARB_LOG_WARN(
                                "Could not find referenced dynamicsMesh: %s", renderMeshPaths[0].GetString().c_str());
                            return true;
                        }

                        parseSoftBodyPrim(prim, mesh, renderMesh, context);
                    }
                    else
                    {
                        CARB_LOG_WARN(
                            "Flex SoftBody with no dynamicsMesh relationship specified or asset could not be generated");
                    }
                }
            }
            else
            {
                CARB_LOG_WARN("Flex SoftBody with no proxyMesh relationship specified or asset could not be generated");
            }
        }
        else
        {
            if (pxr::UsdRelationship rel = prim.GetRelationship(pxr::TfToken("dynamicsMesh")))
            {
                pxr::SdfPathVector paths;
                if (rel.GetTargets(&paths))
                {
                    pxr::UsdPrim mesh(context->stage->GetPrimAtPath(paths[0]));
                    if (!mesh)
                    {
                        CARB_LOG_WARN("Could not find referenced dynamicsMesh: %s", paths[0].GetString().c_str());
                        return true;
                    }

                    parseSoftBodyPrim(prim, mesh, mesh, context);
                }
                else
                {
                    CARB_LOG_WARN(
                        "Flex SoftBody with no dynamicsMesh relationship specified or asset could not be generated");
                }
            }
        }
    }

    return true;
}

void FlexAttach(long int stageId, double metersPerUnit, void* userData)
{
    bool useFlex = iSettings && iSettings->getAsBool("/physics/useFlex");
    if (!useFlex)
        return;

    if (g_flexContext)
    {
        CARB_LOG_ERROR("Attaching Flex to a new stage without detaching");
        return;
    }

    // try and find USD stage from Id
    pxr::UsdStageRefPtr stage = pxr::UsdUtilsStageCache::Get().Find(pxr::UsdStageCache::Id::FromLongInt(stageId));

    if (!stage)
    {
        CARB_LOG_ERROR("Flex could not find USD stage");
        return;
    }

    g_stage = stage;
    g_needResync = false;

    // todo: is there a way to find the physics scene faster?
    // todo: handle case of multiple scenes (multiple flex contexts)
    pxr::UsdPrim scene;
    {
        pxr::UsdPrimRange range = stage->Traverse();

        for (pxr::UsdPrimRange::iterator iter = range.begin(); iter != range.end(); ++iter)
        {
            pxr::UsdPrim prim = *iter;

            pxr::TfToken physicsScene("PhysicsScene");
            if (prim.GetTypeName() == physicsScene)
            {
                pxr::TfToken plugin;
                ReadAttribute(prim, "plugin", &plugin);

                if (plugin == pxr::TfToken("flex"))
                {
                    scene = prim;

                    // just pick the first Flex scene we find
                    break;
                }
            }
        }
    }

    if (!scene)
        return;

    g_flexContext = new FlexContext();
    g_flexContext->init();

    g_flexContext->stage = stage;
    g_flexContext->stageId = stageId;
    g_flexContext->scene = scene;

    FlexBuffers* buffers = g_flexContext->buffers;

    g_flexContext->numNormals = 0;

    // parse USD
    pxr::UsdPrimRange range = stage->Traverse();

    for (pxr::UsdPrimRange::iterator iter = range.begin(); iter != range.end(); ++iter)
    {
        pxr::UsdPrim prim = *iter;

        if (!ParsePrim(stageId, prim, g_flexContext))
        {
            iter.PruneChildren();
        }
    }

    NvFlexSolverDesc desc;
    NvFlexSetSolverDescDefaults(&desc);
    desc.maxParticles = buffers->positions.size();

    // create solver
    g_flexContext->solver = NvFlexCreateSolver(g_flexContext->flexLib, &desc);

    // get default params
    NvFlexGetParams(g_flexContext->solver, &g_flexContext->params);

    // set infinite collision planes
    g_flexContext->params.numPlanes = g_flexContext->numPlanes;
    memcpy(g_flexContext->params.planes, g_flexContext->planes, sizeof(glm::vec4) * g_flexContext->numPlanes);

    // set default solver params
    g_flexContext->params.solverType = eNvFlexSolverPBD;
    g_flexContext->params.numIterations = 20;
    g_flexContext->params.numInnerIterations = 20;

    g_flexContext->interopParticleBuffer =
        g_flexContext->interop->createBuffer(buffers->positions.size() * sizeof(glm::vec3));
#if !NON_SMOOTH_NORMAL_HACK
    g_flexContext->interopNormalBuffer =
        g_flexContext->interop->createBuffer(buffers->normals.size() * sizeof(glm::vec3));
#else
    g_flexContext->interopNormalBuffer =
        g_flexContext->interop->createBuffer(g_flexContext->numNormals * sizeof(glm::vec3));
#endif
    g_flexContext->updateRender();
}

void FlexDetachInternal()
{
    if (g_flexContext)
    {
        NvFlexAcquireContext(g_flexContext->flexLib);

#if USE_INTEROP
        g_flexContext->interop->destroyBuffer(g_flexContext->interopParticleBuffer);
        g_flexContext->interop->destroyBuffer(g_flexContext->interopNormalBuffer);
#endif

        g_flexContext->destroy();

        NvFlexRestoreContext(g_flexContext->flexLib);

        delete g_flexContext;
        g_flexContext = nullptr;
    }
}

void FlexDetach(void* userData)
{
    bool useFlex = iSettings && iSettings->getAsBool("/physics/useFlex");
    if (!useFlex)
        return;

    FlexDetachInternal();
    g_stage = nullptr;
}

void FlexUpdate(float currentTime, float dt, void* userData)
{
    bool useFlex = iSettings && iSettings->getAsBool("/physics/useFlex");
    if (!useFlex)
        return;

    if (g_flexContext)
    {
        // save CUDA context
        NvFlexAcquireContext(g_flexContext->flexLib);

        int numSubsteps = 2;

        pxr::UsdPrim scene = g_flexContext->scene;

        if (scene)
        {
            // update scene params
            ReadAttribute(scene, "numSubsteps", &numSubsteps);
            ReadAttribute(scene, "numIterations", &g_flexContext->params.numIterations);

            ReadAttribute(scene, "gravity", (pxr::GfVec3f*)g_flexContext->params.gravity);
            ReadAttribute(scene, "radius", &g_flexContext->params.radius);
            ReadAttribute(scene, "dynamicFriction", &g_flexContext->params.dynamicFriction);
            ReadAttribute(scene, "relaxationFactor", &g_flexContext->params.relaxationFactor);
            ReadAttribute(scene, "collisionDistance", &g_flexContext->params.collisionDistance);
            ReadAttribute(scene, "shapeCollisionMargin", &g_flexContext->params.shapeCollisionMargin);
            ReadAttribute(scene, "particleCollisionMargin", &g_flexContext->params.particleCollisionMargin);

            int solverType = eNvFlexSolverPBD;
            ReadAttribute(scene, "solver", &solverType);
            g_flexContext->params.solverType = (NvFlexSolverType)solverType;

            ReadAttribute(scene, "wind", (pxr::GfVec3f*)g_flexContext->params.wind);
            ReadAttribute(scene, "drag", &g_flexContext->params.drag);
            ReadAttribute(scene, "lift", &g_flexContext->params.lift);
            ReadAttribute(scene, "damping", &g_flexContext->params.damping);
            ReadAttribute(scene, "maxSpeed", &g_flexContext->params.maxSpeed);

            // set solid radius equal to radius for now (no fluid support)
            g_flexContext->params.solidRestDistance = g_flexContext->params.radius;

            // ensure some minimal margin if not already set
            if (g_flexContext->params.particleCollisionMargin == 0.0f)
                g_flexContext->params.particleCollisionMargin = g_flexContext->params.radius * 0.1f;

            if (g_flexContext->params.shapeCollisionMargin == 0.0f)
                g_flexContext->params.shapeCollisionMargin = g_flexContext->params.radius * 0.1f;
        }

        // update prims from USD, todo: use notifications
        pxr::UsdPrimRange range = g_flexContext->stage->Traverse();

        for (auto prim : range)
        {
            // update FEM materials
            if (strcmp(prim.GetTypeName().GetText(), "SoftMaterial") == 0)
            {
                ParseSoftMaterial(prim, g_flexContext->buffers->tetraMaterials);
            }
        }

        for (FlexSoftBody& inst : g_flexContext->instances)
        {
            if (inst.inflatableOffset != -1)
            {
                ReadAttribute(inst.softbody, "pressure",
                              &g_flexContext->buffers->inflatablePressures[inst.inflatableOffset], 0.1f, 6.0f);
            }

            ReadAttribute(inst.softbody, "attachEnabled", &inst.attachmentsEnabled);
        }

        // step simulation
        g_flexContext->simulate(dt, numSubsteps);

        // restore CUDA context
        NvFlexRestoreContext(g_flexContext->flexLib);
    }
}

void FlexPause(void*)
{
    bool useFlex = iSettings && iSettings->getAsBool("/physics/useFlex");
    if (!useFlex)
        return;
}

void FlexResume(float, void*)
{
    bool useFlex = iSettings && iSettings->getAsBool("/physics/useFlex");
    if (!useFlex)
        return;

    if (!g_stage)
        return;

    if (!g_needResync)
        return;

    long int stageId = pxr::UsdUtilsStageCache::Get().GetId(g_stage).ToLongInt();
    double metersPerUnit = pxr::UsdGeomGetStageMetersPerUnit(g_stage);

    FlexDetachInternal();
    FlexAttach(stageId, metersPerUnit, nullptr);
}

void HandlePrimInternal(const char* primPath)
{
    bool useFlex = iSettings && iSettings->getAsBool("/physics/useFlex");
    if (!useFlex)
        return;

    if (!g_stage)
        return;

    pxr::UsdPrim prim = g_stage->GetPrimAtPath(pxr::SdfPath(primPath));
    if (!prim)
        return;

    pxr::UsdPrimRange range(prim);
    for (auto iter = range.begin(); iter != range.end(); ++iter)
    {
        // check any changes that will trigger flex to resync
        if ((HasSchema(prim, pxr::TfToken("PhysicsAPI"))) || (HasAttribute(prim, pxr::TfToken("FlexRigidAPI"))) ||
            (HasAttribute(prim, pxr::TfToken("enableAttachment"))) || (HasSchema(prim, pxr::TfToken("CollisionAPI"))) ||
            (prim.GetTypeName() == pxr::TfToken("PhysicsScene")) ||
            (strcmp(prim.GetTypeName().GetText(), "SoftBody") == 0))
        {
            g_needResync = true;
            break;
        }
    }
}

void FlexHandlePrimChanged(const char* primPath, const omni::kit::PrimDirtyBits*, void*)
{
    HandlePrimInternal(primPath);
}

void FlexHandlePrimAdded(const char* primPath, void*)
{
    HandlePrimInternal(primPath);
}


void FlexHandlePrimRemoved(const char* primPath, void*)
{
    // if (g_flexContext)
    //  g_flexContext->queueRemoved(primPath);
}

size_t getParticleCount()
{
    return g_flexContext->buffers->positions.size();
}

} // anonymous namespace
} // flex namespace
} // carb namespace

CARB_EXPORT void carbOnPluginStartup()
{
    carb::Framework* framework = carb::getFramework();

    carb::flex::iFastCache = framework->acquireInterface<carb::fastcache::FastCache>();
    carb::flex::iSettings = framework->acquireInterface<carb::settings::ISettings>();

    carb::flex::iSettings->setDefaultBool("/physics/useFlex", true);

    carb::flex::g_stageUpdate = framework->acquireInterface<omni::kit::IStageUpdate>();

    omni::kit::StageUpdateNodeDesc desc = { 0 };
    desc.displayName = "Flex";
    desc.onAttach = carb::flex::FlexAttach;
    desc.onDetach = carb::flex::FlexDetach;
    desc.onUpdate = carb::flex::FlexUpdate;
    desc.onResume = carb::flex::FlexResume;
    desc.onPause = carb::flex::FlexPause;
    desc.onPrimAdd = carb::flex::FlexHandlePrimAdded;
    desc.onPrimChange = carb::flex::FlexHandlePrimChanged;
    desc.onPrimRemove = carb::flex::FlexHandlePrimRemoved;
    carb::flex::g_stageUpdateNode = carb::flex::g_stageUpdate->createStageUpdateNode(desc);
}

CARB_EXPORT void carbOnPluginShutdown()
{
    carb::flex::g_stageUpdate->destroyStageUpdateNode(carb::flex::g_stageUpdateNode);
}

void fillInterface(carb::flex::Flex& iface)
{
    iface.getParticleCount = carb::flex::getParticleCount;
}
