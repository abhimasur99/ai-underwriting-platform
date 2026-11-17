"""Chief state machine: the transition table from docs/architecture.md section 3, as data."""

STATES = [
    "CREATED", "AWAITING_DOCS", "READY", "EXTRACTING", "EXTRACTED", "UNDERWRITING",
    "UNDERWRITTEN", "CHECKING", "CHECKED", "NEEDS_REVIEW", "APPROVED", "SENT_BACK", "REJECTED",
    "RELEASED", "NEEDS_INPUT", "FAILED",
]

TRANSITIONS: set[tuple[str, str]] = {
    ("CREATED", "AWAITING_DOCS"), ("CREATED", "READY"),
    ("AWAITING_DOCS", "AWAITING_DOCS"), ("AWAITING_DOCS", "READY"),
    ("READY", "EXTRACTING"),
    ("EXTRACTING", "EXTRACTED"), ("EXTRACTING", "NEEDS_INPUT"),
    ("NEEDS_INPUT", "AWAITING_DOCS"), ("NEEDS_INPUT", "READY"),
    ("EXTRACTED", "UNDERWRITING"),
    ("UNDERWRITING", "UNDERWRITTEN"), ("UNDERWRITTEN", "CHECKING"),
    ("CHECKING", "CHECKED"), ("CHECKED", "NEEDS_REVIEW"),
    ("CHECKING", "UNDERWRITING"),          # check failed, retries < 2
    ("CHECKING", "NEEDS_REVIEW"),          # check failed, retries = 2: escalate
    ("NEEDS_REVIEW", "APPROVED"), ("APPROVED", "RELEASED"),
    ("NEEDS_REVIEW", "SENT_BACK"), ("SENT_BACK", "UNDERWRITING"),
    ("NEEDS_REVIEW", "REJECTED"),
    ("NEEDS_REVIEW", "UNDERWRITING"),      # a confirmed data patch re-enters here
    ("NEEDS_REVIEW", "NEEDS_INPUT"),       # the reviewer asks the sponsor for something
    ("NEEDS_INPUT", "NEEDS_REVIEW"),       # the sponsor answered in words; nothing to re-extract
}

MAX_RETRIES = 2


class InvalidTransition(RuntimeError):
    pass


def check_transition(current: str, new: str) -> None:
    if new == "FAILED":
        return                              # any state may fail on an unrecoverable error
    if (current, new) not in TRANSITIONS:
        raise InvalidTransition(f"{current} -> {new} is not allowed")
