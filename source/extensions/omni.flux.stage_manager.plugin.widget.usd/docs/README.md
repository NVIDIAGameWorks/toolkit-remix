# omni.flux.stage_manager.plugin.widget.usd

USD-aware tree, state, and action widget plugins for Stage Manager views.

## Responsibilities

- Register reusable USD widget plugins with the Stage Manager factory.
- Provide base classes for widgets that need a USD context or display a state icon.
- Standardize mouse-gesture ownership and selection validation for actionable row icons.

## Non-Responsibilities

- Does not own Stage Manager tree models, selection synchronization, or plugin discovery; those belong to the Stage
  Manager factory and its consumers.
- Does not define which rows an action targets. Action plugins resolve their targets independently.

## Architecture

- `StageManagerUSDWidgetPluginsExtension` registers the built-in prim-tree, visibility, and custom-tags plugins.
- `StageManagerUSDWidgetPlugin` supplies USD context handling for concrete widget plugins.
- `StageManagerStateWidgetPlugin` provides state-icon layout and constructs actionable row icons.
- Concrete plugins render prim data, expose row actions, or contribute context-menu behavior.

### Action Images

Actionable row icons derived from `StageManagerStateWidgetPlugin` should use `make_action_image()`. The factory fixes
the image width to `_icon_size`, defaults its height to `_icon_size`, and accepts a height override for icons that need
visual adjustment. When the image is enabled and has a release callback, the factory owns its press gesture and routes
every press through the existing Stage Manager row interaction. Left and right presses validate selection: a selected
row preserves the current selection, while an unselected row becomes the sole selection before release. The tree
delegate opens the existing context menu for right presses; other buttons do not change selection. Passive and
placeholder images should continue to use `ui.Image` directly so their cells retain normal row interaction.
