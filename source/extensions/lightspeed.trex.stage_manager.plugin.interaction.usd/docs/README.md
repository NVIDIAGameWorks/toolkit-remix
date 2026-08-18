# lightspeed.trex.stage_manager.plugin.interaction.usd

USD interaction plugins that configure the RTX Remix Stage Manager categories and connect them to compatible widgets.

## Responsibilities

- Define the USD interaction layouts for prims, meshes, materials, lights, skeletons, categories, and tags.
- Register the compatible tree, filter, listener, and widget plugins for each interaction.
- Listen for typed ComfyUI events where Stage Manager content must refresh.

## Non-Responsibilities

- Render the tree, filter, or action widgets configured by the interactions.
- Own ComfyUI workflows, submissions, or asynchronous job execution.
- Implement the Stage Manager tree model or USD data services.

## Architecture

- `RemixStageManagerUSDInteractionPlugin` provides the shared Remix USD interaction configuration.
- The `RemixAll*InteractionPlugin` classes specialize that configuration for each Stage Manager category.
- Plugin dependencies provide the concrete tree, filter, listener, and widget implementations selected by each interaction.
