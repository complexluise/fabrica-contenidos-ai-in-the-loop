"""L4 - Adapters de proveedores de video. Una interfaz, N backends."""

from .base import BaseProvider, build_provider

__all__ = ["BaseProvider", "build_provider"]
