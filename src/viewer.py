"""
viewer.py - Image viewer abstraction
Currently supports nomacs backend for frame verification.
"""

import subprocess
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageViewerConfig:
    """Configuration for image viewers."""
    fullscreen: bool = False
    scale: Optional[float] = None  # Percentage, e.g., 100 = 100%
    keep_alive: bool = True  # Block until window closed


class NomacsViewer:
    """nomacs CLI backend for debugging/development."""

    def __init__(self, executable: str = "nomacs"):
        self.executable = executable

    def show_image(self, path: str, config: ImageViewerConfig = None) -> None:
        """Display image with nomacs. Blocks until closed if keep_alive=True."""
        config = config or ImageViewerConfig()

        cmd = [self.executable]

        if config.fullscreen:
            cmd.append("--fullscreen")

        if config.scale:
            cmd.extend(["--scale", str(int(config.scale))])

        cmd.append(path)

        if config.keep_alive:
            # Block until nomacs closes
            subprocess.run(cmd)
        else:
            # Launch detached
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    def cleanup(self) -> None:
        """No cleanup needed for nomacs (subprocess terminates on close)."""
        pass


def get_viewer(backend: str = "nomacs") -> NomacsViewer:
    """Get viewer instance by name."""
    if backend != "nomacs":
        raise ValueError(f"Only 'nomacs' backend is available. Got: {backend}")
    return NomacsViewer()
