# lightspeed.trex.stage_manager.plugin.filter.usd

Provides Remix-specific USD filter plugins for the Stage Manager. Neutral combobox selections, such as All or No Filter,
are skipped before predicate evaluation.

The Remix category filter uses the assignable category subset from `lightspeed.trex.schemas`, so deprecated categories
remain readable for compatibility but are not presented as filter options.
