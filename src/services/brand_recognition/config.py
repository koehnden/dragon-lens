"""
Configuration and constants for brand recognition.

This module contains environment variables, feature flags, and constants
used throughout the brand recognition pipeline.
"""

import os


# Environment variables and feature flags
ENABLE_QWEN_FILTERING = os.getenv("ENABLE_QWEN_FILTERING", "true").lower() == "true"
ENABLE_QWEN_EXTRACTION = os.getenv("ENABLE_QWEN_EXTRACTION", "true").lower() == "true"
# Constants
AMBIGUOUS_CONFIDENCE_THRESHOLD = 0.5
