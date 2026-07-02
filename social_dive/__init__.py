"""
Social Dive — AI-agent internet-access capability layer for 20+ knowledge sources.

An installer, doctor, and config tool with pluggable LLM backends (NVIDIA NIM,
OpenAI, Anthropic) and a Rust performance core.  This is a glue/routing layer:
agents call upstream tools directly after setup.
"""

__version__ = "0.2.0"
__all__ = ["__version__"]
