"""
Recording configuration options for Sediman
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RecordingConfig:
    """Configuration for optimized recording.

    All optimizations are enabled by default for best performance.
    """

    # Core settings
    fps: float = 3.0
    max_duration: int = 300  # seconds

    # Optimization flags
    use_optimized_recorder: bool = True
    enable_disk_storage: bool = True  # Store frames on disk (prevents OOM)
    enable_deduplication: bool = True  # Skip duplicate frames
    adaptive_fps: bool = True  # Adjust FPS based on activity
    enable_action_detection: bool = True  # Detect clicks, inputs, scrolls

    # Quality settings
    jpeg_quality: int = 60  # 0-100
    screenshot_full_page: bool = False  # Only capture viewport

    # Deduplication settings
    similarity_threshold: float = 0.95  # Frames above this similarity are dropped

    # Adaptive FPS settings
    active_fps: float = 10.0  # FPS when user is active
    idle_fps: float = 0.5  # FPS when idle
    activity_window: float = 2.0  # Seconds to consider user active

    # Skill extraction settings
    max_keyframes: int = 15  # Frames sent to LLM (reduced from 25)
    min_keyframes: int = 3

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> RecordingConfig:
        """Create config from dictionary."""
        return cls(
            fps=config.get("fps", 3.0),
            max_duration=config.get("max_duration", 300),
            use_optimized_recorder=config.get("use_optimized_recorder", True),
            enable_disk_storage=config.get("enable_disk_storage", True),
            enable_deduplication=config.get("enable_deduplication", True),
            adaptive_fps=config.get("adaptive_fps", True),
            enable_action_detection=config.get("enable_action_detection", True),
            jpeg_quality=config.get("jpeg_quality", 60),
            screenshot_full_page=config.get("screenshot_full_page", False),
            similarity_threshold=config.get("similarity_threshold", 0.95),
            active_fps=config.get("active_fps", 10.0),
            idle_fps=config.get("idle_fps", 0.5),
            activity_window=config.get("activity_window", 2.0),
            max_keyframes=config.get("max_keyframes", 15),
            min_keyframes=config.get("min_keyframes", 3),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "fps": self.fps,
            "max_duration": self.max_duration,
            "use_optimized_recorder": self.use_optimized_recorder,
            "enable_disk_storage": self.enable_disk_storage,
            "enable_deduplication": self.enable_deduplication,
            "adaptive_fps": self.adaptive_fps,
            "enable_action_detection": self.enable_action_detection,
            "jpeg_quality": self.jpeg_quality,
            "screenshot_full_page": self.screenshot_full_page,
            "similarity_threshold": self.similarity_threshold,
            "active_fps": self.active_fps,
            "idle_fps": self.idle_fps,
            "activity_window": self.activity_window,
            "max_keyframes": self.max_keyframes,
            "min_keyframes": self.min_keyframes,
        }

    def get_optimization_summary(self) -> dict[str, Any]:
        """Get summary of enabled optimizations."""
        return {
            "disk_storage": {
                "enabled": self.enable_disk_storage,
                "benefit": "Prevents out-of-memory crashes by storing frames on disk",
                "tradeoff": "Slightly slower frame access",
            },
            "deduplication": {
                "enabled": self.enable_deduplication,
                "benefit": "Reduces storage by 30-50% by skipping duplicate frames",
                "tradeoff": "Slight CPU overhead for hash computation",
            },
            "adaptive_fps": {
                "enabled": self.adaptive_fps,
                "benefit": "Reduces frames by 50%+ during idle periods",
                "tradeoff": "None - pure improvement",
            },
            "action_detection": {
                "enabled": self.enable_action_detection,
                "benefit": "Better skill extraction with precise action timing",
                "tradeoff": "Minimal overhead from event listeners",
            },
            "max_keyframes": {
                "value": self.max_keyframes,
                "benefit": f"Reduced LLM cost (was 25, now {self.max_keyframes})",
                "tradeoff": "Fewer frames for complex workflows",
            },
        }


# Default instance
DEFAULT_RECORDING_CONFIG = RecordingConfig()
