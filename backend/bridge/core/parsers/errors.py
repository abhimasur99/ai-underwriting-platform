"""Parser errors. Missing or unreadable input fails loudly; nothing is defaulted."""


class ParseError(ValueError):
    """A document could not be read as expected (bad value, unknown status, etc.)."""


class MissingRequiredFieldError(ValueError):
    """Required fields are absent. The chief turns this into NEEDS_INPUT."""

    def __init__(self, missing: list[str]):
        self.missing = list(missing)
        super().__init__("missing required fields: " + ", ".join(self.missing))
