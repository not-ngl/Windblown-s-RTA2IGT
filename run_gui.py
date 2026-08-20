#!/usr/bin/env python3
"""Entry point for the GUI version of Windblown-RTA2LRT."""

import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gui.main import main

if __name__ == "__main__":
    main()
