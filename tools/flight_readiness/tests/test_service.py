"""End-to-end tests for check_flight_readiness.

The predictor tests cover each factor in isolation. These cover the assembled
service: the decision aggregation, the confidence downgrade, and the precedence
rules between them. Written against fakes from tests/fakes.py — no network.

Scenarios to cover (from the Research 2 test table):

    Clear weather, healthy battery, serviced airframe   -> GO, all checks clear
    Forecast gust within the warning band               -> GO_WITH_WARNINGS
    Sustained wind above operational ceiling            -> NO_GO
    Gust above ceiling, sustained wind below            -> NO_GO
    Precipitation forecast, tolerance 0.0 mm/h          -> NO_GO
    Mission duration exceeds projected endurance        -> NO_GO
    Endurance margin inside warning threshold           -> GO_WITH_WARNINGS
    Maintenance OVERDUE                                 -> NO_GO
    Maintenance DUE_SOON                                -> GO_WITH_WARNINGS
    Drone status INIT, not RTF                          -> NO_GO
    Weather source unavailable                          -> UNKNOWN
    Wind above ceiling AND battery unavailable          -> NO_GO   (NO_GO outranks UNKNOWN)
    Valid request 6 days ahead, all clear               -> confidence LOW, recheck set
    Valid request 20 days ahead                         -> UNKNOWN (beyond forecast horizon)
    End time earlier than start time                    -> NEEDS_INFO
    No drone identifier supplied                        -> NEEDS_INFO
    Battery state of health unavailable                 -> GO_WITH_WARNINGS, assumption recorded

Two of these are the ones worth writing first, because they are the rules that
cannot be verified anywhere else:

  - the precedence test, which proves absence of a verdict is never read as approval
  - the 6-days-ahead case, which pins down whether LOW confidence downgrades GO

Blocked on service.py. Add the tests as the service takes shape.
"""
