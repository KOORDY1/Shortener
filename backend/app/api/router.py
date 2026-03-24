"""Compatibility shim: aggregate v1 API routes."""

from app.api.v1.router import router

__all__ = ["router"]
