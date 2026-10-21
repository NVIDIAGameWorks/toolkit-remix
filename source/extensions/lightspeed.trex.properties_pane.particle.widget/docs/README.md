# lightspeed.trex.properties_pane.particle.widget

Properties panel for `RemixParticleSystem` prims.

## Responsibilities

- Builds schema-grouped particle rows, seeds selected legacy animated values before Curve editing, and forwards pane
  visibility and selection to the shared USD property widget.
- Declares each logical row's animated attributes and associated legacy companions.
- Configures grouped curve editor outlets and semantic channel styles for particle size, velocity, and rotation speed.

## Non-Responsibilities

- Does not own Curve sessions or floating windows; concrete editors and the
  [shared window](../../omni.flux.property_widget_builder.delegates/docs/README.md#floating-property-editors) own them.
- The application stylesheet, `lightspeed.trex.app.style`, owns the channel palette.

Clipboard handling and undo grouping belong to the shared property helper. USD row models and commands own value
application; this panel does not implement another copy/paste path.

## Architecture

`ParticleSystemPropertyWidget` populates the USD model and delegate from the particle schema and prepares legacy
attributes for the selected Curve targets.

Legacy companion ownership comes from `PARTICLE_LEGACY_ANIMATION_MAPPINGS`: size and rotation each own four
spawn/target fields, each color gradient owns two, and velocity owns none. Copy/paste transfers both representations
independently without opening editors or seeding animation. See
[logical row editing](../../omni.flux.property_widget_builder.model.usd/docs/README.md#logical-row-editing)
for the shared application contract.

`PARTICLE_EDIT_GROUPS` describes curve IDs, grouping, display names, and leaf `label_style_name` values. The
[USD curve field builder](../../omni.flux.property_widget_builder.model.usd/docs/README.md#curve-layout-styling)
adapts that layout and opens the Curve Editor.

Channel style assignments are Python UI configuration, not USD schema metadata or authored curve payloads.

## Usage

```python
from lightspeed.trex.properties_pane.particle.widget import ParticleSystemPropertyWidget

particle_properties_widget = ParticleSystemPropertyWidget(context_name="")

particle_properties_widget.refresh(particle_system_paths)
particle_properties_widget.show(True)

particle_properties_widget.expand_all_groups()
particle_properties_widget.collapse_all_groups()
```

## Integration

Add the extension as a dependency, construct the widget in your pane, and refresh it when particle selection changes.
See the [integration example](INTEGRATION_EXAMPLE.md).
