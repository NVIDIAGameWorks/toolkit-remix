# Overview

This is the widget that creates a properties panel for RemixParticleSystem prim types.

## Usage

```python
from lightspeed.trex.properties_pane.particle.widget import ParticleSystemPropertyWidget

# Create the widget
particle_properties_widget = ParticleSystemPropertyWidget(context_name="")

# Refresh with particle system prim paths
particle_properties_widget.refresh(particle_system_paths)

# Show/hide the widget
particle_properties_widget.show(True)
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
