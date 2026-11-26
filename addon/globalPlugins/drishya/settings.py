"""Validated options, independent of NVDA's configuration implementation."""
from dataclasses import dataclass

ADDON_VERSION = "0.2.1"
MODEL_NAME = "SmolVLM2 500M"

CONFIG_SPEC = {
    "detail": "option('concise', 'detailed', default='concise')",
    "max_side": "integer(min=256, max=1536, default=1024)",
    "threads": "integer(min=1, max=12, default=4)",
    "speak": "boolean(default=True)",
    "setup_prompt_version": "string(default='')",
}


@dataclass(frozen=True)
class Options:
    detail: str = "concise"
    max_side: int = 1024
    threads: int = 4
    speak: bool = True

    def __post_init__(self):
        if self.detail not in ("concise", "detailed"):
            raise ValueError("Invalid description style.")
        if not 1 <= self.threads <= 12 or not 256 <= self.max_side <= 1536:
            raise ValueError("Threads must be 1–12 and image size must be 256–1536 pixels.")
