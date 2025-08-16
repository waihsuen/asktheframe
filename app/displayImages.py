# displayImages.py — simplified (no cache, no preprocessing)
import os
import sys
import time
import logging
import glob
from typing import List, Optional
from PIL import Image

# ---------------- Config (env-tunable) ----------------
FRAME_SUB_PATH = os.getenv("FRAME_SUB_PATH", "base")
FRAME_PATTERN = os.getenv("FRAME_PATTERN", "frame_*.bmp")
FRAME_ZPAD = int(os.getenv("FRAME_ZPAD", "2"))  # zero-pad width for {n}, e.g., 2 => frame01.bmp
IMAGE_REFRESH_SECONDS = float(os.getenv("IMAGE_REFRESH_SECONDS", "15"))

# Base dirs
BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PIC_DIR = os.path.join(BASE_DIR, "images")
FRAMES_DIR = os.path.join(BASE_DIR, "images", "frames", FRAME_SUB_PATH)


# ---------------- Image utils ----------------
def _fmt_frame_name(n: int) -> str:
    """Render the filename for a frame index (1-based) using pattern and zero padding."""
    if FRAME_ZPAD > 0:
        return FRAME_PATTERN.format(n=str(n).zfill(FRAME_ZPAD))
    return FRAME_PATTERN.format(n=n)


def _sorted_frame_paths() -> List[str]:
    """
    Auto-discover frames from FRAMES_DIR:
    - Use FRAME_PATTERN as a glob pattern directly.
    - Else use IMAGE_COUNT (1..N) to build names.
    - Else fall back to all .bmp files.
    """
    # Use glob pattern directly if provided
    if any(t in FRAME_PATTERN for t in ("*", "?", "[")):
        paths = sorted(glob.glob(os.path.join(FRAMES_DIR, FRAME_PATTERN)))
        return [p for p in paths if os.path.isfile(p)]

    # Optional explicit count
    try:
        count = int(os.getenv("IMAGE_COUNT", "0"))
    except ValueError:
        count = 0

    if count > 0:
        return [os.path.join(FRAMES_DIR, _fmt_frame_name(i)) for i in range(1, count + 1)]

    # Last resort: all BMPs in FRAMES_DIR (alphabetical)
    return sorted(glob.glob(os.path.join(FRAMES_DIR, "*.bmp")))


# ---------------- Sequencer ----------------
class ImageSequencer:
    """
    Handles frame discovery, in-memory index, and showing frames.
    No caching; assumes frames are already 800x480 1-bit BMPs.
    """

    def __init__(self):
        self._paths: List[str] = _sorted_frame_paths()
        self._index: int = 0  # 0-based
        if self._paths:
            logging.debug(
                "ImageSequencer: found %d frames (%s ... %s)",
                len(self._paths),
                os.path.basename(self._paths[0]),
                os.path.basename(self._paths[-1]),
            )
        else:
            logging.debug("ImageSequencer: found 0 frames")

    def reload(self):
        """Re-scan the images directory and keep index within bounds."""
        self._paths = _sorted_frame_paths()
        if self._paths:
            self._index %= len(self._paths)
        else:
            self._index = 0

    def has_frames(self) -> bool:
        return len(self._paths) > 0

    def current_path(self) -> Optional[str]:
        if not self._paths:
            return None
        return self._paths[self._index]

    def advance(self):
        if not self._paths:
            return
        self._index = (self._index + 1) % len(self._paths)

    def show_next(self, epd) -> bool:
        """Show current frame then advance; sleep between frames."""
        if not self._paths:
            logging.info("No frames found in images directory")
            time.sleep(IMAGE_REFRESH_SECONDS)
            return False

        path = self.current_path()
        if not path:
            time.sleep(IMAGE_REFRESH_SECONDS)
            return False

        try:
            # Files are preprocessed to correct size/mode — just open and display
            with Image.open(path) as img:
                epd.display(epd.getbuffer(img))
        except Exception as e:
            logging.error(f"EPD display error for {path}: {e}")
            # Skip this frame to prevent stalls
            self.advance()
            time.sleep(IMAGE_REFRESH_SECONDS)
            return False

        logging.info(
            "Displayed %s (%d/%d)",
            os.path.basename(path),
            self._index + 1,
            len(self._paths),
        )
        self.advance()
        time.sleep(IMAGE_REFRESH_SECONDS)
        return True


# A single module-level sequencer instance for compatibility with your current main.py
_SEQUENCER = ImageSequencer()


# ---------------- Public API ----------------
def show_image(epd, img_path: str):
    """
    Manual display helper for a single image path.
    Assumes image is already 800x480, mode '1'.
    """
    if not os.path.exists(img_path):
        logging.warning("Image not found: %s", img_path)
        return False
    try:
        with Image.open(img_path) as img:
            epd.display(epd.getbuffer(img))
        return True
    except Exception as e:
        logging.error("EPD display error for %s: %s", img_path, e)
        return False


def show_image_loop(epd):
    """
    Show the next discovered frame from FRAMES_DIR and advance.
    Honors IMAGE_REFRESH_SECONDS for delay between frames.
    """
    if not _SEQUENCER.has_frames():
        _SEQUENCER.reload()
    return _SEQUENCER.show_next(epd)


def show_sleep(epd):
    """
    Draw sleep.bmp from images/, put panel to sleep, then wait.
    """
    path = os.path.join(PIC_DIR, "sleep.bmp")
    return show_image(epd, path)
