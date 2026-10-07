class AnalyticsError(Exception):
    """An actionable, transport-independent analytical failure."""

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)

    def as_dict(self):
        return {"code": self.code, "message": self.message}
