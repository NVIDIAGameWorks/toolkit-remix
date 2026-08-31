# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0]
### Added
- Created in-process DDS encoding through the NVTT 3 library, with a typed block format, gamma correct mip
  interpolation, and GPU 0 pinned on every encoding thread. Each worker thread's cached NVTT context is released
  when that thread exits.
