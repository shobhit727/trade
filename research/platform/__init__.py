"""Foundational primitives for isolated, reproducible quantitative research."""

from .domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from .experiments import ExperimentSpec

__all__ = [
    "AlgorithmFamily",
    "DataResolution",
    "ExperimentSpec",
    "Market",
    "ResearchTrack",
]
