from enum import Enum


class OverallDecision(str, Enum):
    # Final result returned by the compliance tool
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    BLOCK = "BLOCK"
    NEEDS_INFO = "NEEDS_INFO"
    UNKNOWN = "UNKNOWN"


class CheckResult(str, Enum):
    # The result of one individual waypoint compliance check
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"
    UNAVAILABLE = "UNAVAILABLE"
