"""Mock AI analysis service.

Simulates the Orchestration + Issue Intelligence + Decision layers from the
architecture diagram (Waste / Drainage / Safety agents -> severity scoring ->
Gemini-style recommendation) so the prototype can be demoed without a backend.

Results are deterministic per image (seeded by the image bytes) so a given
snapshot always analyzes the same way during a recording.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from random import Random

# The detector agents shown in the architecture diagram.
AGENTS: tuple[dict, ...] = (
    {"key": "waste", "name": "Waste Agent", "icon": "🗑️", "label": "Waste / Garbage"},
    {"key": "drainage", "name": "Drainage AI Agent", "icon": "🌊", "label": "Drainage / Flooding"},
    {"key": "safety", "name": "Safety Agent", "icon": "🕳️", "label": "Open Manhole / Hazard"},
)

_SEVERITY_ORDER = {"High": 3, "Medium": 2, "Low": 1}

_RECOMMENDATIONS = {
    "waste": "Dispatch sanitation crew for garbage clearance; schedule recurring pickup for this zone.",
    "drainage": "Deploy drainage-clearing team before next rainfall; inspect upstream blockage.",
    "safety": "Barricade the open manhole immediately and flag for urgent repair — public safety risk.",
}


@dataclass
class Detection:
    """A single issue detected by one agent."""

    agent: str
    issue_type: str
    confidence: float          # 0.0 - 1.0
    severity: str              # High | Medium | Low
    recommendation: str


@dataclass
class AnalysisResult:
    """Full output of an analysis run for one snapshot."""

    latitude: float
    longitude: float
    detections: list[Detection]
    summary: str
    analyzed_at: str
    thumbnail: object = None   # PIL image, optional (for dashboard/incidents)
    meta: dict = field(default_factory=dict)

    @property
    def top_severity(self) -> str:
        """Highest severity across all detections (Low if none)."""
        if not self.detections:
            return "Low"
        return max(self.detections, key=lambda d: _SEVERITY_ORDER[d.severity]).severity

    def to_metadata(self) -> dict:
        """JSON-serializable view persisted as Cloud Storage object metadata.

        This is what the Dashboard / Reported Incidents screens read back to
        rebuild incidents from the bucket, so it carries every field those
        screens need (detections, per-detection status, summary, timestamp).
        """
        return {
            "analyzed_at": self.analyzed_at,
            "summary": self.summary,
            "detections": [
                {
                    "agent": d.agent,
                    "issue_type": d.issue_type,
                    "confidence": d.confidence,
                    "severity": d.severity,
                    "status": "Open",
                    "recommendation": d.recommendation,
                }
                for d in self.detections
            ],
        }


def _seed_from_image(image_bytes: bytes) -> int:
    """Derive a stable seed from image content."""
    digest = hashlib.sha256(image_bytes).hexdigest()
    return int(digest[:8], 16)


def analyze(
    image_bytes: bytes,
    latitude: float,
    longitude: float,
    thumbnail: object = None,
) -> AnalysisResult:
    """Run the (simulated) multi-agent analysis on a snapshot."""
    rng = Random(_seed_from_image(image_bytes))

    detections: list[Detection] = []
    for agent in AGENTS:
        # Each agent independently decides whether it found its issue.
        if rng.random() < 0.6:
            confidence = round(rng.uniform(0.71, 0.98), 2)
            if confidence >= 0.9:
                severity = "High"
            elif confidence >= 0.8:
                severity = "Medium"
            else:
                severity = "Low"
            detections.append(
                Detection(
                    agent=agent["name"],
                    issue_type=agent["label"],
                    confidence=confidence,
                    severity=severity,
                    recommendation=_RECOMMENDATIONS[agent["key"]],
                )
            )

    if detections:
        top = max(detections, key=lambda d: _SEVERITY_ORDER[d.severity])
        summary = (
            f"{len(detections)} issue(s) detected. "
            f"Highest severity: {top.severity} — {top.issue_type}. "
            "Gemini recommends prioritizing this location for municipal action."
        )
    else:
        summary = "No civic issues detected. Location appears clear."

    return AnalysisResult(
        latitude=latitude,
        longitude=longitude,
        detections=detections,
        summary=summary,
        analyzed_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        thumbnail=thumbnail,
        meta={"agents_run": len(AGENTS)},
    )
