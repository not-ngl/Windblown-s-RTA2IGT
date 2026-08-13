"""
Speedrun Load Time Detector Package

A hybrid manual/automatic tool for detecting and measuring loading times
in speedrun video analysis.
"""

__version__ = '1.0.0'
__author__ = 'Speedrun Community'

from src.core import (
    LoadingSegment,
    AnalysisResult,
    LoadTimeAnalyzer,
)

__all__ = [
    'LoadingSegment',
    'AnalysisResult',
    'LoadTimeAnalyzer',
]

