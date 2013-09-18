"""Shims provide interfaces between tests and external dependencies.

Example: Mongobox is required for some of our tests. Rather than scattering
Mongobox usage throughout our code, use the Mongo shim in this directory to
handle Mongobox setup, usage, and tear-down.
"""
