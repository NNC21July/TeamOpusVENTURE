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
    unavailable_reasons: list[str] = []
    single_frame_video_notes: list[str] = []

    for media in media_items:
        try:
            raw_detections = detection_client.get_detections_for_media(media=media)
        except DetectionDataUnavailableError as exc:
            # Use the exception's own message rather than assuming a cause —
            # it already distinguishes "unsupported media type" from a
            # genuine service/network error, and those are very different
            # situations for a pilot reading the result.
            unavailable_media.append(media.media_id)
            unavailable_reasons.append(f"{media.media_id}: {exc}")
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

        if media.media_type == "video":
            # GarudaDetectionClient runs video through a single
            # Garuda-selected representative frame, not the full video — a
            # real finding, but not full coverage. Surfaced here (not in the
            # detection client) because only this layer knows what "partial"
            # means for the response as a whole.
            single_frame_video_notes.append(
                f"{media.media_id}: video summarized via a single representative "
                "frame — full video review not yet supported."
            )

    # Order findings chronologically where we have timestamps, so a caller
    # reading through them gets a coherent narrative, not an arbitrary listing.
    findings.sort(key=lambda f: f.captured_at or media_items[0].captured_at or "")

    if not findings:
        # Was previously hardcoded to "Geo AI Config Service was
        # unreachable for all media in this flight" regardless of cause —
        # misleading when the real reason was e.g. every item being an
        # unsupported media type (video), not a service outage.
        return SummarizeFlightResponse(
            flight_id=request.flight_id,
            status=SummaryStatus.UNKNOWN,
            media_count=len(media_items),
            notes=tuple(unavailable_reasons),
        )

    status = (
        SummaryStatus.PARTIAL
        if unavailable_media or single_frame_video_notes
        else SummaryStatus.COMPLETE
    )
    notes = tuple(unavailable_reasons) + tuple(single_frame_video_notes)

    return SummarizeFlightResponse(
        flight_id=request.flight_id,
        status=status,
        media_count=len(media_items),
        findings=tuple(findings),
        notes=notes,
    )
