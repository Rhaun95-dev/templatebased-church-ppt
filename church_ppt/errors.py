class AppError(Exception):
    status = 500

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status


class ConversionError(AppError):
    status = 422


class StorageUnavailable(AppError):
    status = 503


class NotFound(AppError):
    status = 404
