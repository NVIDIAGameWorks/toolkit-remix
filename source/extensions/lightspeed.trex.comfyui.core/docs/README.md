# lightspeed.trex.comfyui.core

Core ComfyUI integration for RTX Remix Toolkit. The extension owns server access, workflow contracts, graph creation,
file transfer, persistence, and output Apply behavior.

## Responsibilities

- Connect to an external ComfyUI server and load RTX Remix workflows.
- Parse tagged inputs and outputs from workflow metadata.
- Resolve texture and mesh inputs from a selection, the stage, or a Constant.
- Upload textures and models through the ComfyUI input image endpoint.
- Upload `.usd`, `.usda`, and `.usdc` layers with their file dependencies. Preserve source layers and remap copied asset paths.
- Download image results from the `images` history channel and mesh results from the `3d` history channel through the ComfyUI view endpoint.
- Select the texture or asset pipeline from tagged output metadata.
- Build one typed job graph for each resolved source candidate.
- Register all job, result, resolver, target, receipt, and handler codecs.
- Apply texture and model changes only at one terminal graph job.
- Reconcile pending Apply work for each explicit USD context.

## Non-Responsibilities

- Does not render the AI Tools UI. `lightspeed.trex.comfyui.widget` owns that surface.
- Does not execute or store the shared queue. `omni.flux.job_queue.core` owns that work.
- Does not define Remix model and texture processing steps. `lightspeed.trex.asset_pipeline.core` owns them.
- Does not define general texture or reference mutations.
- Does not implement tagging outputs until the RTX Remix node pack defines their result contract.
- Does not install or manage a ComfyUI process.

## Architecture

```text
ComfyUICore
    |
    +-- texture outputs --> ComfyUIJob --> texture processing (terminal texture Apply)
    |
    +-- one mesh output -> ComfyUIAssetJob --> Prepare --> textures --> mesh (terminal asset Apply)
```

### Key Classes

- `ComfyUICore` resolves candidates and builds output-driven graphs for one USD context.
- `ComfyUICore.prepare_submission(prim_paths)` returns a `ComfyUISubmission` with the built graphs and skip
  counts. `submit_prepared_submission` adds the whole batch in one queue transaction and returns a
  `ComfyUISubmissionResult`. `get_retarget_state` returns a `ComfyUIRetargetState` for the Retarget action.
- `ComfyUIAPI` uploads inputs, submits prompts, reads history, and downloads declared files.
- `WorkflowOutput` stores Apply Behavior and Texture Type.
- `SelectedMeshResolver` stores input Reference Selection: All references of the mesh, or only the Selected one.
- `AllStageMeshesResolver` uses that input choice for every mesh with external references in the stage.
- `ComfyUIJob` returns a texture pipeline request.
- `ComfyUIAssetJob` returns a mesh pipeline request. Standalone texture outputs travel in `extra_textures`.
- The mesh graph has four jobs: ComfyUI generation, Optimization preparation, Texture optimization, and Mesh optimization.
- `MeshOptimizationResult` contains the optimized model and its `texture_result` for asset Apply.
- `ComfyUITextureApplyHandler` replaces only configured texture outputs.
- `ComfyUIAssetApplyHandler` adds or replaces model references through `Setup` and replaces textures in one undo group.
- Constant-only asset graphs use the terminal asset Apply handler for metadata. They do not mutate the stage.

### Output Contract

- `texture_file_path` outputs use the texture pipeline.
- `mesh_file_path` selects the asset pipeline. A workflow can have only one mesh output.
- A workflow can also have multiple texture outputs.
- The output node ID is the stable processing key. Texture Type remains editable and does not define identity.
- Every tagged file output produces exactly one final file.
- Mesh inputs select a Constant file, Selected Mesh, or All Meshes.
- Reference Selection is a mesh input setting, not an output setting. **All** uses every reference of the mesh.
  **Selected** uses only the reference that composes the picked prim, and rejects a pick that is under none.
  Selected Mesh defaults to **Selected**. All Meshes defaults to **All**.
- Replace (default when the workflow has a mesh input) upscales each selected reference in place. The references of
  a mesh are the ones authored on the `mesh_<hash>` prim plus the ones on its marked `ref_<id>` children, which is
  what the Selection panel lists. Picking any prim under any of them selects the mesh. With Reference Selection
  **All**, a mesh with four references submits four jobs, and each job replaces the reference it was created from.
  A reference on the `mesh_<hash>` prim is replaced by a new marked `ref_<id>` child that composes the result. A
  reference on a `ref_<id>` child is swapped on that child: the child keeps its path, no sibling is created, and
  no empty `ref_<id>` prim remains. Replace requires a mesh input, so a text- or image-to-mesh workflow defaults to
  Append.
- Append adds the result beside the source reference. It does not need a reference choice.
- Do Nothing still processes and publishes the file. It does not change the stage.
- Constant-only sources publish local or remote `.meta` sidecars without stage mutation.
- Metadata sidecars record the pipeline's actual `validation_passed` outcome.
- Asset workflows publish standalone texture outputs beside the optimized model in the same output directory.

### Released Records

Queue records from version 3.0.5 retain their texture input bindings and `ComfyUIJobApplyHandler` identity.
The released handler uses the current texture Apply behavior.
Constant asset graphs use one Apply state for mesh and texture metadata. Revert restores both sets of sidecars together.
These graphs retain the captured project target but do not change stage references or texture fields. That target is
deliberate: a Constant-model job has exactly one Apply, one Revert, and one Apply policy, like every other asset job,
so its sidecars publish only while the submitting project is open and follow the global automatic Apply setting.
Publishing after the project is closed or switched is not supported.

### Apply Safety

Apply captures the project, edit layer, texture fields, and sidecar content before mutation. Reapply accepts only the
original or applied state: every owner has a Remix reference child that composes the generated model (or, for a
`ref_<id>` owner replaced in place, the owner itself composes it and carries this job's marker), or none does.
A failed Apply undoes its undo group and restores the attempt metadata. Revert removes the generated children,
restores the original texture fields, and restores each processed texture's prior sidecar. Revert of a Replace is
composed-equivalent: the source model returns as a Remix reference child of its owner, or on the `ref_<id>` owner
itself when Apply replaced it in place.
