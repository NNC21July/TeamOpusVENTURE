from enum import Enum


class MaintenanceStatus(str, Enum):
    # Airworthiness status derived from a drone's maintenance records.
    # Owned by get_drone_maintenance_status (Tool 2); imported by the
    # flight readiness airworthiness predictor so the two tools agree on
    # a single set of values.
    OK = "OK"
    DUE_SOON = "DUE_SOON"
    OVERDUE = "OVERDUE"
    NEEDS_INFO = "NEEDS_INFO"
    UNKNOWN = "UNKNOWN"
