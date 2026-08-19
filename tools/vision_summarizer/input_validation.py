from dataclasses import dataclass

from tools.vision_summarizer.request_response_schemas import SummarizeFlightRequest


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_request(request: SummarizeFlightRequest) -> ValidationResult:
    errors: list[str] = []

    if not isinstance(request.flight_id, str) or not request.flight_id.strip():
        errors.append("flight_id must be a non-empty string")

    if request.focus is not None and (not isinstance(request.focus, str) or not request.focus.strip()):
        errors.append("focus, if provided, must be a non-empty string")

    return ValidationResult(errors=tuple(errors))
