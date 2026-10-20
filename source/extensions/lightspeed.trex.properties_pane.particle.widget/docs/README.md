# Overview

This is the widget that creates a properties panel for RemixParticleSystem prim types.

## Responsibilities

- Build particle property groups and curve/gradient outlets from the particle schema.
- Declare each logical row's animated attributes and associated legacy companions.

## Non-Responsibilities

Clipboard handling and undo grouping belong to the shared property helper. USD row models and commands own value
application; this panel does not implement another copy/paste path.

## Architecture

`ParticleSystemPropertyWidget` builds ordinary USD items and logical outlets. Legacy companion ownership comes from
`PARTICLE_LEGACY_ANIMATION_MAPPINGS`: size and rotation each own four spawn/target fields, each color gradient owns
two, and velocity owns none. Copy/paste transfers both representations independently without opening editors or seeding
animation. See [logical row editing](../../omni.flux.property_widget_builder.model.usd/docs/README.md#logical-row-editing)
for the shared application contract.

## Usage

```python
from lightspeed.trex.properties_pane.particle.widget import ParticleSystemPropertyWidget

# Create the widget
particle_properties_widget = ParticleSystemPropertyWidget(context_name="")

# Refresh with particle system prim paths
particle_properties_widget.refresh(particle_system_paths)

# Show/hide the widget
particle_properties_widget.show(True)

# Bulk-toggle grouped property rows
particle_properties_widget.expand_all_groups()
particle_properties_widget.collapse_all_groups()
```

## Features

- **Organized Groups**: Properties are organized into logical groups defined in the schema.

- **Real-time Updates**: Automatically updates when USD attributes change

- **Custom Display Names**: User-friendly names for technical attributes

- **Tooltips**: Helpful descriptions for each property

## Integration

This widget can be integrated into existing properties panes by:

1. Adding it as a dependency to your properties pane extension
2. Creating an instance in your pane's UI
3. Connecting it to selection change events
4. Refreshing it when RemixParticleSystem prims are selected

See the [INTEGRATION_EXAMPLE.md](INTEGRATION_EXAMPLE.md) for an example.
