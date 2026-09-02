"""Test package marker.

Present so pytest can tell same-named modules apart — §14 names both
`tests/core/rubrics/test_versioning.py` and
`tests/core/submissions/test_versioning.py`, and without these the second
fails to import over the first.
"""
