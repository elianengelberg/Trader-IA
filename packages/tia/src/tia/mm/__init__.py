"""Market making — proposes quotes, never executes on its own authority.

Every module here sits *before* the existing authority chain (evidence, risk, execution)
and produces either measurements or proposals. Nothing in this package can reach a live
execution provider: the runtime refuses one at construction, and the feature flags
default to off. See docs/MARKET_MAKING_AUDIT.md for the plan and its phases.
"""
