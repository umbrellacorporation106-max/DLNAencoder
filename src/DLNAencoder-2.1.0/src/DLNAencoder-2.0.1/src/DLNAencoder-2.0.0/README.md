# DLNAencoder

A professional, batch video encoder dashboard for Arch Linux, optimized for DLNA/Roku compatibility.

## Features

- **Curses Dashboard UI**: A robust, stable terminal dashboard for real-time monitoring.
- **Real-time Metrics**: Live tracking of batch progress, file encoding, ETA, encoding speed, CPU frequency, and system temperature.
- **Robust Controls**: Single-key input for pause ('p'), resume ('r'), and quit ('q').
- **CPU Throttling**: Manage system resources effectively with automated CPU frequency limits.
- **Automatic Batch Processing**: Queue multiple files and process them sequentially.
- **Graceful Termination**: Clean exit management with proper terminal state restoration and child process cleanup.

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
- `python-curses` (usually part of python3 distribution)

## Usage

You can use the `encode` command to start the batch encoding process. You can specify a path or use the default:

```bash
encode [path/to/video/or/directory]
```
