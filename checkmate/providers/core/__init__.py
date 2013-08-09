'''Core Provider

Defined:
script   - a script configuration provider

'''

from checkmate import providers


def register():
    '''Register package providers.'''
    from checkmate.providers.core import script
    providers.register_providers([script.Provider])
