"""RubriQ domain logic.

Zero Streamlit imports live under this package. That rule is invariant #9 and
it is enforced by ``tests/core/test_no_streamlit_in_core.py``, not by good
intentions. If a module in here needs configuration or the acting user, it
receives them as arguments.
"""
