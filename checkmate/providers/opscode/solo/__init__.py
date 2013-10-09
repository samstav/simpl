from checkmate import exceptions


class SoloProviderNotReady(exceptions.CheckmateException):
    """Expected data are not yet available."""
    pass