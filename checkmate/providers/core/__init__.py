"""Core Provider

Defined:
script   - ca script configuration provider

"""

from checkmate.providers import register_providers


def register():
    from checkmate.providers.core.script import Provider as script
    register_providers([script])
