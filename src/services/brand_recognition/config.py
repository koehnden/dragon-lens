"""
Configuration and constants for brand recognition.

This module contains environment variables, feature flags, and constants
used throughout the brand recognition pipeline.
"""

import os


# Environment variables and feature flags
ENABLE_QWEN_FILTERING = os.getenv("ENABLE_QWEN_FILTERING", "true").lower() == "true"
ENABLE_QWEN_EXTRACTION = os.getenv("ENABLE_QWEN_EXTRACTION", "true").lower() == "true"
ENABLE_EMBEDDING_CLUSTERING = os.getenv("ENABLE_EMBEDDING_CLUSTERING", "false").lower() == "true"
ENABLE_LLM_CLUSTERING = os.getenv("ENABLE_LLM_CLUSTERING", "false").lower() == "true"
ENABLE_WIKIDATA_NORMALIZATION = os.getenv("ENABLE_WIKIDATA_NORMALIZATION", "false").lower() == "true"
ENABLE_BRAND_VALIDATION = os.getenv("ENABLE_BRAND_VALIDATION", "false").lower() == "true"
ENABLE_CONFIDENCE_VERIFICATION = os.getenv("ENABLE_CONFIDENCE_VERIFICATION", "false").lower() == "true"
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qllama/bge-small-zh-v1.5:latest")

# Constants
AMBIGUOUS_CONFIDENCE_THRESHOLD = 0.5
