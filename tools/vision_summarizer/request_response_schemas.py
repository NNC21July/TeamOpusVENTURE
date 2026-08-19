from dataclasses import dataclass, field
from datetime import datetime

from tools.vision_summarizer.decision_types import DetectionShape, SummaryStatus


@dataclass(frozen=True)
class SummarizeFlightRequest:
    # Information required to summarize a flight's captured media
    flight_id: str
    focus: str | None = None  # e.g. "defects only" vs. "general summary"


@dataclass(frozen=True)
class MediaItem:
    # Trimmed view of a Full_Media record — only what the pipeline needs,
    # not the full raw schema (see Research 2 notes on why).
    media_id: str
    media_type: str
    url: str | None = None
    captured_at: datetime | None = None
    gps: tuple[float, float] | None = None  # (lat, lon), from exif if present


@dataclass(frozen=True)
class RawDetection:
    # One detection as returned by Geo AI's /ml_detections/upload or
    # GET /ml_detections, before any descriptor processing.
    media_id: str
    object_label: str
    score: float
    shape: DetectionShape
    bbox: tuple[float, float, float, float] | None = None       # x, y, w, h (ratios)
    polygon: tuple[tuple[float, float], ...] | None = None       # [(x, y), ...] ratios
    frame_time_s: float | None = None      # offset into video, if applicable
    track_id: str | None = None            # cross-frame identity, if Garuda provides one


@dataclass(frozen=True)
class DescribedDetection:
    # A detection after the descriptor layer has run: raw geometry has
    # been converted into something an LLM can use directly, and
    # near-duplicate detections (e.g. the same object across many video
    # frames) have already been collapsed into one entry.
    object_label: str
    score: float
    position: str                          # e.g. "upper-left", "near center"
    relation: str | None = None            # e.g. "adjacent to the facade" (if a reference object was available)
    occurrence_count: int = 1              # how many raw detections this entry represents
    first_seen_s: float | None = None
    last_seen_s: float | None = None


@dataclass(frozen=True)
class MediaFinding:
    # Findings for a single piece of media, after descriptor processing
    media_id: str
    captured_at: datetime | None
    detections: tuple[DescribedDetection, ...] = ()


@dataclass(frozen=True)
class SummarizeFlightResponse:
    # NOTE: deliberately has no `summary` / prose field. This tool returns
    # structured, deduplicated, plain-language-described findings only —
    # per team decision, the calling model (Claude Desktop) writes the
    # actual pilot-facing summary from `findings` itself, rather than this
    # tool making a second internal LLM call.
    flight_id: str
    status: SummaryStatus
    media_count: int = 0
    findings: tuple[MediaFinding, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
