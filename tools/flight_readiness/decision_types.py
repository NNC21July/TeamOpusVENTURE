from enum import Enum


class OverallDecision(str, Enum):
    # Final result returned by the flight readiness tool
    GO = "GO"
    GO_WITH_WARNINGS = "GO_WITH_WARNINGS"
    NO_GO = "NO_GO"
    NEEDS_INFO = "NEEDS_INFO"
    UNKNOWN = "UNKNOWN"


class CheckResult(str, Enum):
    # The result of one individual readiness check.
    # CLEAR rather than PASS: PASS is the overall verdict of the route
    # compliance tool, and the model sees both tools in one conversation.
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class ConfidenceLevel(str, Enum):
    # How much the assessment should be trusted. Categorical, not numeric:
    # there are no historical outcomes to calibrate a probability against.
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
