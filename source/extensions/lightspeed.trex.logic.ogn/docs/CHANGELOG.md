(changelog_lightspeed.trex.components.ogn)=

# Changelog

This document records all notable changes to the **lightspeed.trex.logic.ogn** extension.

The format is based on [Keep a Changelog](https://keepachangelog.com). The project adheres to [Semantic Versioning](https://semver.org).

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
