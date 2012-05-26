"""Custome Exceptions for CheckMate

To be serialization-friendly, call the Exception __init__ with any extra
attributes:

class CheckmateCustomException(Exception):
    def __init__(self, something_custom):
        super(CheckmateCustomException, self).__init__(something_custom)
        self.something_custom = something_custom

"""


class CheckmateException(Exception):
    pass


class CheckmateDatabaseMigrationError(Exception):
    pass
