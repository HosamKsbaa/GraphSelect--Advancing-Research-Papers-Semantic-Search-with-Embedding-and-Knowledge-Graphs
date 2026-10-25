"""Engines: deterministic research building blocks with one public entry point each.

Code outside this package imports only `engines.<name>` (the package `__init__`), never
internal modules. Engines never import routers, services, or agent code; see
`tests/engines/test_engine_boundaries.py`.
"""
