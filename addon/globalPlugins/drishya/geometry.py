"""Screen rectangles in physical desktop coordinates."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self):
        if any(not isinstance(v, int) or isinstance(v, bool)
               for v in (self.x, self.y, self.width, self.height)):
            raise ValueError("Screen coordinates must be whole numbers.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("This object has no visible image area.")

    def clip(self, desktop):
        left, top = max(self.x, desktop.x), max(self.y, desktop.y)
        right = min(self.x + self.width, desktop.x + desktop.width)
        bottom = min(self.y + self.height, desktop.y + desktop.height)
        if right <= left or bottom <= top:
            raise ValueError("This object is outside the visible screen. Bring it into view and try again.")
        return Rect(left, top, right - left, bottom - top)


def fitted_size(width, height, max_side):
    if min(width, height, max_side) <= 0:
        raise ValueError("Image dimensions must be positive.")
    scale = min(1.0, max_side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))
