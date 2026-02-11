(changelog_lightspeed.trex.components.ogn)=

# Changelog

This document records all notable changes to the **lightspeed.trex.logic.ogn** extension.

The format is based on [Keep a Changelog](https://keepachangelog.com). The project adheres to [Semantic Versioning](https://semver.org).

## [1.0.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.0.1]
### Changed
- Switched to ruff for linting and formatting

## [1.0.0]
### Changed
- REMIX-4241: Rewriting premake5.lua to source node files from target-deps/omni_core_materials/lightspeed.trex.logic.
- REMIX-4241: Bumped runtime version.

### Removed
- REMIX-4241: All local node files in python/nodes directory since they come from target-deps/omni_core_materials now.

## [0.0.4]
### Changed
- Moves type resolution logic to a util file that is called from each node.
- Refactors type resolution logic to prevent invalid connections from being made.
- Adds token category validation to prevent invalid connections from being made.

## [0.0.3]
### Changed
- Update node schema to match omni_core_materials ext-83e59c6-main

## [0.0.2]
### Changed
- Updated node schema to match current runtime.

## [0.0.1]
### Initial Version
- Created based on omni.graph.template.python-1.40.0
