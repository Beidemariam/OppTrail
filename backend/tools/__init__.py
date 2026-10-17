"""Operational entry points, run as `python -m tools.<name>` by the Makefile.

A real package rather than a directory of scripts since R.7, for one concrete
reason: `tools/seed.py` imports `tools.scale` (the corpus `make seed-scale`
and `tests/test_performance.py` share), and without this file mypy resolves
the same source as both `scale` and `tools.scale` and refuses to check
either.
"""
