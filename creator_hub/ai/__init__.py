"""Optional AI enhancement layer.

The Creator Data Hub core must remain fully usable without this package being configured.
"""

from .service import AICopilot

__all__ = ["AICopilot"]
