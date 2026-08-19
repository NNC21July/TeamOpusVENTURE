from tools.vision_summarizer.client_protocol import (
    DetectionClient,
    DetectionDataUnavailableError,
    MediaClient,
    MediaDataUnavailableError,
)
from tools.vision_summarizer.decision_types import SummaryStatus
from tools.vision_summarizer.descriptors.dedup import dedupe_detections
from tools.vision_summarizer.input_validation import validate_request
from tools.vision_summarizer.request_response_schemas import (
    MediaFinding,
    SummarizeFlightRequest,
    SummarizeFlightResponse,
)


def summarize_flight(
    *,
    request: SummarizeFlightRequest,
    media_client: MediaClient,
    detection_client: DetectionClient,
) -> SummarizeFlightResponse:
    """Fetch a flight's media, get detections for each item, and return
    deduplicated, plain-language-described findings.

    No LLM call happens inside this function. By team decision, the calling
    model (Claude Desktop) writes the pilot-facing prose summary itself from
    the structured `findings` this returns — this tool's job stops at
    handing over clean, deduplicated, already-described data.
    """
    validation = validate_request(request)
    if not validation.is_valid:
        return SummarizeFlightResponse(
            flight_id=request.flight_id,
            status=SummaryStatus.NEEDS_INFO,
            missing_inputs=validation.errors,
        )

    try:
        media_items = media_client.get_media_for_flight(flight_id=request.flight_id)
    except MediaDataUnavailableError:
        return SummarizeFlightResponse(
            flight_id=request.flight_id,
            status=SummaryStatus.UNKNOWN,
            notes=("Media Asset Service was unreachable for this flight.",),
        )

    if not media_items:
        return SummarizeFlightResponse(
            flight_id=request.flight_id,
            status=SummaryStatus.NO_MEDIA,
        )

    findings: list[MediaFinding] = []
    unavailable_media: list[str] = []

    for media in media_items:
        try:
            raw_detections = detection_client.get_detections_for_media(media=media)
        except DetectionDataUnavailableError:
            unavailable_media.append(media.media_id)
            continue

        # Descriptor layer: raw geometry -> plain-language position, and
        # near-duplicate detections across frames collapsed into one entry
        # per real-world object. See descriptors/spatial.py and dedup.py.
        described = dedupe_detections(raw_detections)

        findings.append(
            MediaFinding(
                media_id=media.media_id,
                captured_at=media.captured_at,
                detections=tuple(described),
            )
        )

    # Order findings chronologically where we have timestamps, so a caller
    # reading through them gets a coherent narrative, not an arbitrary listing.
    findings.sort(key=lambda f: f.captured_at or media_items[0].captured_at or "")

    if not findings:
        return SummarizeFlightResponse(
            flight_id=request.flight_id,
            status=SummaryStatus.UNKNOWN,
            media_count=len(media_items),
            notes=("Geo AI Config Service was unreachable for all media in this flight.",),
        )

    status = SummaryStatus.PARTIAL if unavailable_media else SummaryStatus.COMPLETE
    notes = (
        (f"Detections unavailable for {len(unavailable_media)} media item(s): "
         f"{', '.join(unavailable_media)}",)
        if unavailable_media
        else ()
    )

    return SummarizeFlightResponse(
        flight_id=request.flight_id,
        status=status,
        media_count=len(media_items),
        findings=tuple(findings),
        notes=notes,
    )
