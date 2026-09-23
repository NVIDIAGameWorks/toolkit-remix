# lightspeed.layer_manager.core

Core project and layer management for a named USD context.

## Responsibilities

- Query the layer hierarchy and Remix layer types.
- Open and close projects; create, move, remove, mute, lock, save, and select edit-target layers.
- Provide validated request and response models for layer services.

## Non-Responsibilities

REST routing belongs to [lightspeed.layer_manager.service](../../lightspeed.layer_manager.service/docs/README.md).
This extension does not provide layer management UI.

## Architecture

`LayerManagerCore` operates on its USD context; `ILayer` implementations handle Remix layer types.
`LayerModel` describes each returned layer, including its identifier, type, children, and `muted` state.

Layer tree, type-filtered, and immediate-sublayer queries report `muted` from the stage's explicit mute state.
Muted layers remain discoverable. Muting a parent does not mark its children as explicitly muted.
Callers of the static `get_sublayers_with_data_models()` method should pass `context_name` to read the intended stage;
omitting it uses the default context.
