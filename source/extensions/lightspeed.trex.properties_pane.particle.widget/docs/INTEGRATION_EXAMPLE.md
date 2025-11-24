# Integration Example

This example shows how to integrate the ParticleSystemPropertyWidget into an existing properties pane.

## Adding to Asset Replacements Pane

Here's how to modify the `AssetReplacementsPane` to include particle system properties. This general approach
also applies to other property panes.

### 1. Add Dependency

In your properties pane's `config/extension.toml`, add:

```toml
[dependencies]
"lightspeed.trex.properties_pane.particle.widget" = {}
```

### 2. Import the Widget

In your pane's `setup_ui.py`:

```python
from lightspeed.trex.properties_pane.particle.widget import ParticleSystemPropertyWidget
```

### 3. Add to UI

In the `__create_ui` method, add after the material properties section:

```python
# Particle System Properties
self._particle_properties_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
    "PARTICLE SYSTEM PROPERTIES",
    info_text="Properties of selected RemixParticleSystem prims.\n\n"
    "- Shows particle system attributes like gravity, speed, and turbulence\n"
    "- Properties are organized into logical groups\n"
    "- Changes are applied in real-time",
    collapsed=True,
    pinnable=True,
    pinned_text_fn=lambda: self._get_selection_pin_name(for_particles=True),
    unpinned_fn=self._refresh_particle_properties_widget,
)
self._collapsible_frame_states[CollapsiblePanels.PARTICLE_PROPERTIES] = True
with self._particle_properties_collapsable_frame:
    self._particle_properties_widget = ParticleSystemPropertyWidget(self._context_name)
```

### 4. Add to Enum

Add to your `CollapsiblePanels` enum:

```python
class CollapsiblePanels(Enum):
    BOOKMARKS = 0
    HISTORY = 1
    LAYERS = 2
    MATERIAL_PROPERTIES = 3
    MESH_PROPERTIES = 4
    SELECTION = 5
    PARTICLE_PROPERTIES = 6  # Add this line
```

### 5. Add Refresh Method

Add a method to refresh particle properties:

```python
def _refresh_particle_properties_widget(self):
    """Refresh the particle properties widget based on current selection"""
    if not self._particle_properties_widget:
        return

    usd_context = omni.usd.get_context(self._context_name)
    stage = usd_context.get_stage()
    if not stage:
        return

    # Get selected prims
    selected_paths = usd_context.get_selection().get_selected_prim_paths()
    particle_system_paths = []

    # Filter for RemixParticleSystem prims
    for path in selected_paths:
        prim = stage.GetPrimAtPath(path)
        if prim.HasAPI(PARTICLE_SCHEMA_NAME):
            particle_system_paths.append(path)

    # Refresh the widget
    self._particle_properties_widget.refresh(particle_system_paths)
```

### 6. Connect to Selection Events

In your selection change handler:

```python
def _on_tree_selection_changed(self, items):
    # ... existing code ...

    # Refresh particle properties
    self._refresh_particle_properties_widget()
```

### 7. Update Pin Name Method

Update your `_get_selection_pin_name` method:

```python
def _get_selection_pin_name(self, for_materials: bool = False, for_particles: bool = False) -> str:
    # ... existing code for materials ...

    if for_particles:
        # Count particle system prims
        particle_count = 0
        for path in selected_paths:
            prim = stage.GetPrimAtPath(path)
            if prim.IsValid() and prim.GetTypeName() == "RemixParticleSystem":
                particle_count += 1

        if particle_count == 1:
            return "1 Particle System"
        elif particle_count > 1:
            return f"{particle_count} Particle Systems"
        else:
            return "No Particle Systems"

    # ... rest of existing code ...
```

### 8. Add to Destroy Method

In your `destroy` method:

```python
def destroy(self):
    # ... existing code ...

    if self._particle_properties_widget:
        self._particle_properties_widget.destroy()
```

## Usage

Once integrated, the particle system properties will appear in the properties pane when RemixParticleSystem prims are selected, showing all the particle system attributes organized into logical groups.
