"""Collapses repeated per-frame detections into one entry per real-world object.

A 10-minute video sampled at even a low frame rate can produce hundreds of raw
detections for what is really the same person or defect seen continuously.
Returning all of them to the calling model burns tokens and produces a
repetitive, unreadable summary. This module groups raw detections into one
DescribedDetection per distinct object, tracking how many frames it appeared
in and its time span.

Preferred path: if Geo AI supplies a `track_id` (the same object keeps a
consistent id across frames), grouping is exact — just group by track_id.
Fallback path: if no track_id is available, group detections that share a
label and stay spatially close within a short time window, on the assumption
that a big spatial or temporal jump means it's a different object.
"""

from dataclasses import dataclass

from tools.vision_summarizer.descriptors.spatial import centroid_of, describe_position, describe_relation
from tools.vision_summarizer.request_response_schemas import DescribedDetection, RawDetection

_DEFAULT_SPATIAL_THRESHOLD = 0.08   # centroid distance, in frame-ratio units
_DEFAULT_TIME_GAP_S = 2.0           # max gap between frames to still count as "same object"


@dataclass
class _Cluster:
    label: str
    detections: list[RawDetection]

    @property
    def best(self) -> RawDetection:
        # Represent the cluster with its highest-confidence detection
        return max(self.detections, key=lambda d: d.score)

    @property
    def times(self) -> list[float]:
        return [d.frame_time_s for d in self.detections if d.frame_time_s is not None]


def dedupe_detections(
    detections: list[RawDetection],
    *,
    reference: RawDetection | None = None,
    spatial_threshold: float = _DEFAULT_SPATIAL_THRESHOLD,
    time_gap_s: float = _DEFAULT_TIME_GAP_S,
) -> list[DescribedDetection]:
    """Group raw detections (possibly spanning many video frames or images)
    into one DescribedDetection per distinct real-world object.

    `reference` is an optional detection (e.g. the facade/structure box) used
    to add a relational description ("near the facade") on top of the plain
    grid position — see descriptors.spatial.describe_relation.
    """
    if not detections:
        return []

    has_track_ids = all(d.track_id is not None for d in detections)
    clusters = (
        _cluster_by_track_id(detections)
        if has_track_ids
        else _cluster_by_proximity(detections, spatial_threshold=spatial_threshold, time_gap_s=time_gap_s)
    )

    described: list[DescribedDetection] = []
    for cluster in clusters:
        anchor = cluster.best
        times = cluster.times
        described.append(
            DescribedDetection(
                object_label=cluster.label,
                score=anchor.score,
                position=describe_position(anchor),
                relation=describe_relation(anchor, reference),
                occurrence_count=len(cluster.detections),
                first_seen_s=min(times) if times else None,
                last_seen_s=max(times) if times else None,
            )
        )
    return described


def _cluster_by_track_id(detections: list[RawDetection]) -> list[_Cluster]:
    by_track: dict[str, _Cluster] = {}
    for detection in detections:
        cluster = by_track.setdefault(
            detection.track_id, _Cluster(label=detection.object_label, detections=[])
        )
        cluster.detections.append(detection)
    return list(by_track.values())


def _cluster_by_proximity(
    detections: list[RawDetection], *, spatial_threshold: float, time_gap_s: float
) -> list[_Cluster]:
    ordered = sorted(detections, key=lambda d: (d.frame_time_s if d.frame_time_s is not None else 0.0))

    open_clusters: list[_Cluster] = []

    for detection in ordered:
        match = _find_matching_open_cluster(
            detection, open_clusters, spatial_threshold=spatial_threshold, time_gap_s=time_gap_s
        )
        if match is not None:
            match.detections.append(detection)
        else:
            open_clusters.append(_Cluster(label=detection.object_label, detections=[detection]))

    return open_clusters


def _find_matching_open_cluster(
    detection: RawDetection,
    open_clusters: list[_Cluster],
    *,
    spatial_threshold: float,
    time_gap_s: float,
) -> _Cluster | None:
    detection_time = detection.frame_time_s if detection.frame_time_s is not None else 0.0
    detection_centroid = centroid_of(detection)

    for cluster in open_clusters:
        if cluster.label != detection.object_label:
            continue
        last = cluster.detections[-1]
        last_time = last.frame_time_s if last.frame_time_s is not None else 0.0
        if detection_time - last_time > time_gap_s:
            continue
        last_centroid = centroid_of(last)
        distance = (
            (detection_centroid[0] - last_centroid[0]) ** 2
            + (detection_centroid[1] - last_centroid[1]) ** 2
        ) ** 0.5
        if distance <= spatial_threshold:
            return cluster
    return None
