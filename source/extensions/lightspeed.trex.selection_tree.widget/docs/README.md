# lightspeed.trex.selection_tree.widget

Displays the selected asset hierarchy in the Property Panel, including context-menu actions for copying added lights
and pasting them through mesh asset, descendant, or instance selections.

The selection tree uses direct children of `/RootNode/meshes` as mesh asset roots. Nested replacement names retain their owner item.
Shared mesh path checks still accept standalone capture meshes and other stage roots.
