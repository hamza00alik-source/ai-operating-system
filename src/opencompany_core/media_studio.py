"""Video-production capability registry; providers are never enabled implicitly."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapabilityState(StrEnum):
    RESEARCHED = "researched_not_connected"
    CONFIGURED = "configured_not_tested"
    VERIFIED = "verified"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class VideoCapability:
    key: str
    display_name: str
    state: CapabilityState
    generation_modes: tuple[str, ...]
    execution_requirements: tuple[str, ...]
    zero_budget_path: str
    safety_controls: tuple[str, ...]


LONGCAT_VIDEO = VideoCapability(
    key="longcat-video",
    display_name="LongCat-Video",
    state=CapabilityState.RESEARCHED,
    generation_modes=("text_to_video", "image_to_video", "video_continuation"),
    execution_requirements=(
        "CUDA-capable NVIDIA GPU with compatible drivers",
        "PyTorch and model-specific dependencies",
        "Downloaded model weights and sufficient local storage",
        "A supervised worker with bounded resource usage",
    ),
    zero_budget_path=(
        "Evaluate an already-available user-controlled GPU or a genuinely free hosted GPU allocation; "
        "do not download large weights or launch metered compute until resource and cost checks pass."
    ),
    safety_controls=(
        "No paid GPU, hosted inference, or API usage without separate owner approval",
        "Generated assets remain drafts until reviewed",
        "Check model and asset licences before commercial use",
        "Publishing and customer-facing claims require owner approval",
    ),
)


def video_capabilities() -> tuple[VideoCapability, ...]:
    return (LONGCAT_VIDEO,)
