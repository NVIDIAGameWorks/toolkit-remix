# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.0]
### Changed
- Auto-save now defaults to off.
- Auto-save now prompts before saving, with options to save, skip the current save, or stop prompting for the app session.

## [1.0.1]
### Changed
- Applied new lint rules
- Updated LayerManagerCore calls

## [1.0.0]
### Added
- Auto-save extension that periodically saves all dirty layers in the active project
- Preferences page under Edit > Preferences > Auto-Save with enable/disable toggle and interval selector
- Interval presets: 30 seconds, 1 minute, 5 minutes (default), 10 minutes, 30 minutes, 1 hour, or custom
- Custom interval field supporting seconds, minutes, or hours
- In-app notification displayed after each auto-save
