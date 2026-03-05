"""Vercel serverless function entry point — exposes FastAPI app as ASGI."""
from app.main import app  # noqa: F401 — Vercel detects the ASGI app
