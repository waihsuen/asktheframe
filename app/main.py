# main.py
import os, sys, time, signal, logging
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

import displayBuses
import displayImages

load_dotenv()
ASIA_SG = ZoneInfo("Asia/Singapore")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LIB_DIR = os.path.join(BASE_DIR, "libraries")
if os.path.exists(LIB_DIR):
    sys.path.append(LIB_DIR)

try:
    from waveshare_epd import epd7in5_V2  # type: ignore
except ImportError as e:
    print(f"Could not import waveshare_epd: {e}")
    raise

# ---- Config ----
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
REFRESH_SECONDS = int(os.getenv("LOOP_REFRESH_SECONDS", "30"))
SLEEP_START_H = int(os.getenv("SLEEP_START_H", "0"))
SLEEP_END_H = int(os.getenv("SLEEP_END_H", "8"))
IMAGES_PER_CYCLE = int(os.getenv("IMAGES_PER_CYCLE", "2"))
NIGHT_LOOP_SECONDS = int(os.getenv("NIGHT_LOOP_SECONDS", "1800"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
print("=== Application starting ===")
logging.info("Logging initialized")

_shutdown = False


def _handle_term(signum, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_term)


def is_sleep_hours(now: datetime) -> bool:
    """Return True if current time is within the configured night window."""
    h = now.hour
    if SLEEP_START_H > SLEEP_END_H:
        # e.g., 19 -> 7 (wrap midnight)
        return (h >= SLEEP_START_H) or (h < SLEEP_END_H)
    else:
        # e.g., 22 -> 23 (same day window)
        return SLEEP_START_H <= h < SLEEP_END_H


def _wait_with_sigterm(seconds: float):
    """Sleep up to 'seconds' but wake quickly on SIGTERM."""
    waited = 0.0
    step = 0.5
    while waited < seconds and not _shutdown:
        time.sleep(min(step, seconds - waited))
        waited += step


def main():
    logging.info("Main Init")
    epd = epd7in5_V2.EPD()
    epd.init()
    epd.Clear()

    loop_i = 0

    try:
        while not _shutdown:
            loop_i += 1
            t0 = time.monotonic()
            now = datetime.now(ASIA_SG)
            logging.info("========== Loop %d ==========", loop_i)
            logging.debug("now=%s hour=%d", now, now.hour)

            # ----- Night / Sleep window -----
            if is_sleep_hours(now):
                logging.info("Night window: show sleep image, then panel sleep.")
                try:
                    displayImages.show_sleep(epd)  # draws sleep.bmp only (no sleep/wait)
                except Exception:
                    logging.exception("sleep image failed (continuing)")

                # ensure low power while we wait longer than normal
                try:
                    epd.sleep()
                except Exception:
                    logging.exception("epd.sleep() failed")

                logging.info("Night wait %ds", NIGHT_LOOP_SECONDS)
                _wait_with_sigterm(NIGHT_LOOP_SECONDS)

                # Wake panel only if we will draw again
                if not _shutdown:
                    try:
                        epd.init()
                    except Exception:
                        logging.exception("epd.init() after night failed")
                continue

            # ----- Daytime updates -----
            # Show some images, then buses (reduces refreshes vs both every loop)
            logging.info("=== Image Display x%d ===", IMAGES_PER_CYCLE)
            for _ in range(max(1, IMAGES_PER_CYCLE)):
                if _shutdown:
                    break
                displayImages.show_image_loop(epd)
                time.sleep(0.1)  # tiny spacing, panel already busy

            logging.info("=== Bus Display ===")
            displayBuses.show_bus_arrivals(epd)

            # ----- Power saving between loops -----
            try:
                epd.sleep()  # only sleep once per loop
            except Exception:
                logging.exception("epd.sleep() failed")

            _wait_with_sigterm(REFRESH_SECONDS)

            # Wake only if we’re going to draw again
            if not _shutdown:
                try:
                    epd.init()
                except Exception:
                    logging.exception("epd.init() failed")

            dt = time.monotonic() - t0
            logging.debug("Loop %d time: %.2fs", loop_i, dt)

    except KeyboardInterrupt:
        logging.info("Exiting (KeyboardInterrupt)")
    finally:
        try:
            epd.Clear()
        except Exception:
            pass
        try:
            epd7in5_V2.epdconfig.module_exit(cleanup=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
