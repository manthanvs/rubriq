"""The AI layer.

The ONLY package where an LLM SDK may be imported (invariant #9 territory,
section 6.1). Everything outside it calls the plain functions in
``core.ai.provider`` and never sees a prompt, an SDK, or a graph.

Phase 5a is deliberately graph-free: a direct call, the response contract, and
the evidence guard. LangGraph arrives in 5b as an upgrade to a path that
already works.
"""
