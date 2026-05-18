# Changelog

All notable changes to this project will be documented in this file.

## [2.0.1] - 2026-05-17
### Fixed
- **Finalization Bug**: Restored missing logic to move encoded files to destination and remove original source files.
- **Collision Prevention**: Added unique temporary filenames to prevent file collisions during encoding.

## [2.0.0] - 2026-05-16
### Added
- **Curses Dashboard**: Completely refactored UI for a robust, stable terminal dashboard.
- **Real-time Metrics**: Integrated CPU Frequency (GHz), Temperature monitoring, and dynamic ETA calculations.
- **Visual Improvements**: Added progress bars (Overall and Current file) with numerical percentages.
- **Robust Controls**: Implemented single-key input ('p' to pause, 'r' to resume, 'q' to quit) with proper terminal state restoration.
- **Process Management**: Enhanced child process handling for aggressive, clean termination on exit or interrupt.
- **FFmpeg Silence**: Fully redirected process output for a clean terminal environment.
- **Installation Automation**: Automated sudoers configuration for `cpupower` within `install.sh`.
