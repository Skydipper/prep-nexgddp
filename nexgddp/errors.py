"""ERRORS"""


class Error(Exception):

    def __init__(self, message):
        self.message = message

    @property
    def serialize(self):
        return {
            'message': self.message
        }


class SqlFormatError(Error):
    pass


class GeostoreNotFound(Error):
    pass


class PeriodNotValid(Error):
    pass


class TableNameNotValid(Error):
    pass


class GeostoreNeeded(Error):
    pass


class XMLParserError(Error):
    pass


class InvalidField(Error):
    pass


class InvalidCoordinates(Error):
    pass


class CoordinatesNeeded(Error):
    pass


class LayerNotFound(Error):
    pass


class DatasetNotFound(Error):
    pass


class RasdamanError(Error):
    pass
