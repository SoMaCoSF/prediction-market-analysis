"""Vercel serverless entrypoint for the GYST Control Center FastAPI app.

Vercel's Python runtime exposes each file under api/ as a serverless
function. This module re-exports the FastAPI `app` defined in the
repo-root server.py so the API is served from this function.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server import app  # noqa: E402,F401  (re-exported for Vercel)
