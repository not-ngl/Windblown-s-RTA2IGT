# Windblown-s-RTA2IGT

A tool designed to help speedrun.com moderators identify and remove loading times from *Windblown* run submissions. 
Combines automated detection with manual verification workflows for timing extraction.
Can also be used by users.

> **Note:** Windblown-s-RTA2IGT is an assist tool and cannot replace human verification.

## Features

- **GUI support** — Simple GUI to run including the entire workflow
- **Spectrogram Visualization** — Audio-based waveform display to quickly locate loading regions
- **Automatic Boundary Expansion** — Expands anchor points into start/end timestamps using color analysis
- **Frame-Accurate Verification** — Keyboard navigation for sub-second precision (30fps video support)
- **Multi-Segment Support** — Process multiple loading times in a single submission
- **Cross-Platform** — Tested on Linux should work on Windows (macOS compatibility pending user reports)
- **Standardized Export** — Generates output files that could be used for quick moderation verification
- **YouTube Integration** — Download videos directly from URLs via yt-dlp

## System Requirements

### Core Dependencies

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.10+ | Required for type hints and async support |
| FFmpeg | Any recent build | Must be accessible in system PATH |

### Python Packages

Install via `pip install -r requirements.txt`:

- `PySide6` — GUI framework
- `Pillow` — Image processing and text overlays
- `opencv-python` — Spectrogram rendering
- `scipy` — Audio signal processing
- `numpy` — Numerical computations
- `yt-dlp` — Video download from URLs

### Platform Status

| Platform | Status | Notes |
|----------|--------|-------|
| Linux | Fully tested | Recommended environment |
| Windows |⚠️Should work | May require FFmpeg PATH configuration |
| macOS | Untested | Community feedback needed |

## Installation

### Clone the repository

```
git clone https://github.com/yourusername/Windblown-s-RTA2IGT.git
cd Windblown-s-RTA2IGT
```

### Verify FFmpeg
Ensure FFmpeg is installed and accessible:
```
ffmpeg -version
ffprobe -version
```
If not found, install FFmpeg from ffmpeg.org and add to system PATH.

### Install Python Dependencies
```
pip install -r requirements.txt
```

### Run
The GUI starts with:
```
python src/gui/main.py
```

## Usage

1. **Provide a video** and load it
2. **Use the Spectrogram** to find loading regions (mark segments where in-game timer is active; they appear quiet/black)
3. **Let the tool auto-detect** the approximate boundaries
4. **Locate precise frames** using h/j/k/l keys to find the first visible purple loading frame
5. **Export** — output files help moderators verify the results

> **Note:** Windblown-s-RTA2IGT is an assist tool and cannot replace human verification.

## License

This project is licensed under the **MIT License**, see the LICENSE file for full details.

### Important Notes

- **"Windblown"** is the property of Motion Twin and is not affiliated with this project.
- **Windblown-s-RTA2IGT** is a community tool. It is not affiliated with or endorsed by the game studio.
- **yt-dlp** should be used solely for downloading submitted runs for moderation purposes.
- This tool is provided **as-is, without warranty**. It is an assist tool and cannot replace human verification during moderation.
