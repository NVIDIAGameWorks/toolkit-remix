# omni.flux.stage_manager.plugin.filter.usd

Provides reusable USD filter plugins for the Stage Manager, including search, visibility, prim-type, custom tag, and
additional filter UI plugins. Combobox filter tooltips describe the available options so users can choose filters without
opening each dropdown first. Neutral filter states, such as an empty search field or All Prims visibility, are skipped
before predicate evaluation. Search terms containing `/` match full USD prim paths literally before regex detection; other
terms match prim names and nicknames, with regex metacharacters including backslash enabling regex matching. Additional
Filters reset user-editable values without changing hidden UI placement flags.
