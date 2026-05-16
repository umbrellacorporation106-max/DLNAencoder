# DLNAencoder

A sleek, batch video encoder dashboard for Arch Linux, optimized for DLNA/Roku compatibility.

## Features

- **Dashboard UI**: Monitor your encoding progress in real-time.
- **CPU Throttling**: Manage system resources effectively during heavy encoding tasks.
- **Automatic Batch Processing**: Queue multiple files and let the encoder handle them sequentially.
- **Integrity Checks**: Ensure your encoded files are valid and ready for playback.

## Installation

To install DLNAencoder, run the installation script:

```bash
./install.sh
```

## Usage

You can use the `encode` command to start the process. You can specify a path or use the default:

```bash
encode [path/to/video/or/directory]
```

## Dependencies

DLNAencoder requires the following tools to be installed:

- `ffmpeg`
- `ffprobe`
- `cpupower`
- `python3`
- `psutil`
