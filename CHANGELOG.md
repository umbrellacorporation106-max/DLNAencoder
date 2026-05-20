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

## [2.0.2] - 2026-05-18
### Fixed
- **CPU Throttling**: Restored missing logic for CPU frequency limiting and automatic restoration on exit.

## [2.2.1] - 2026-05-19
### Fixed
- **CPU Throttle Management**: Refactored throttle logic to apply frequency limits without forcing specific governors, preventing conflicts with existing system power states.
- **UI Persistence**: Resolved UI collision issue where summary message obscured metrics, and ensured robust summary rendering.
- **Encoding Queue**: Fixed regression in file selection logic ensuring only checked files are processed.
- **Session Persistence**: Implemented 'Interruption Memory' to save batch results to disk after force-quits.
- **Throttle Toggle Crash**: Implemented asynchronous thread-based execution for CPU frequency commands to prevent UI freezes.

## [2.2.0] - 2026-05-19
### Added
- **Interactive Help Screen ('h')**: A new overlay accessible in any state that lists all available controls and hotkeys.
- **Return to Selection Menu ('m')**: New hotkey available in the FINISHED state to re-scan the input directory and start a new batch without restarting the program.
- **Improved State Transitions**: Refined the flow between SELECTING, ENCODING, and FINISHED states for better reliability.

### Fixed
- **Selection Persistence**: Fixed a bug where deselected files were still being processed in the encoding queue.
- **UI Footers**: Added missing 'h' and 'm' hints to the status bar for better discoverability.

## [2.1.0] - 2026-05-18
### Added
- **Interactive Selection State**: New startup screen allows checking/unchecking files with spacebar.
- **Manual File Addition ('a')**: Hotkey to manually add specific files or directories to the queue.
- **Dynamic Configuration ('c')**: Change and persist the default input directory directly from the dashboard.
- **Live CPU Toggle ('t')**: Switch between throttled and full CPU speed during runtime.
- **UI Enhancements**: Added version tag v2.1.0 to header and improved layout spacing.
- **State Management**: Distinct SELECTING, ENCODING, and FINISHED states for better user feedback.
