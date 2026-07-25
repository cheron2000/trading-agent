"""communication.events — Events published at the Communication Layer (L2).

These events are deliberately placed in L2 so they can be imported by
any higher layer (L3–L7) without creating forbidden cross-layer
dependencies.
"""

from .portfolio_state_event import PortfolioStateEvent

__all__ = ("PortfolioStateEvent",)
