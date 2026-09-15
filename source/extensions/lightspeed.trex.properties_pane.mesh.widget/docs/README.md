# lightspeed.trex.properties_pane.mesh.widget

Object Properties reset indicators show default USD values through the shared USD property delegate.

The widget exposes `expand_all_groups()` and `collapse_all_groups()` so embedding property panes can bulk-toggle both
transform and object property groups from a section header menu.

Displays properties for selected replacement meshes, including active Remix render categories.

When render categories are displayed, active deprecated decal categories are automatically migrated to `Decal`, the
display label for `remix_category:decal_Static`. The migration disables the deprecated attributes, applies the
canonical category to every displayed mesh, and is grouped into one composition-safe undoable operation. Undo removes
only opinions introduced by the migration, preserving weaker composed decal opinions.
