# DLNAencoder

A professional, batch video encoder dashboard for Arch Linux, optimized for DLNA/Roku compatibility.

## Features

- **Interactive File Selection**: Choose exactly which files to encode using an intuitive selection screen.
- **Curses Dashboard UI**: A robust, stable terminal dashboard for real-time monitoring.
- **Real-time Metrics**: Live tracking of batch progress, file encoding, ETA, encoding speed, CPU frequency, and system temperature.
- **Dynamic Configuration**: Change your default input directory or add manual paths directly from the UI.
- **Live CPU Controls**: Toggle CPU throttling on-the-fly to manage system resources.
- **Automatic Batch Processing**: Process your selected queue sequentially with automated file finalization.
- **Graceful Termination**: Clean exit management with proper terminal state restoration and child process cleanup.

## Controls

### Global
- **'h'**: Toggle the interactive Help Screen (overlay).
- **'t'**: Toggle CPU throttling (on/off).
- **'q'**: Quit the application.

### Selection Screen
- **Up/Down Arrows**: Navigate the file list.
- **Spacebar**: Toggle file selection `[X]`.
- **'a'**: Manually add a file or directory path.
- **'c'**: Change the default input directory (saved to config).
- **'s'**: Set custom throttle speed (GHz).
- **Enter**: Start encoding selected files.

### Encoding Dashboard
- **'p'**: Pause encoding.
- **'r'**: Resume encoding.

### Finished Screen
- **'m'**: Return to Selection Menu (re-scans directory).

## Installation

1. Run the installation script:
   ```bash
   ./install.sh
   ```
2. Restart your terminal or run `source ~/.bashrc` (or `.zshrc`) to load the `encode` alias.

## Dependencies

DLNAencoder requires the following tools to be installed:

- `ffmpeg`
- `ffprobe`
- `cpupower`
- `python3`
- `python-psutil`

## Usage

You can use the `encode` command to start the application:

```bash
encode
```
You can also specify a path as an argument to override the default:
```bash
encode [path/to/video/or/directory]
```
