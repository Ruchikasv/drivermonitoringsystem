"""
Audible beep generation for distraction alerts.

Plays an audible notification in a non-blocking background thread.
Uses winsound on Windows or sounddevice if available.
"""

import logging
import platform
import threading

from app.distraction import config

logger = logging.getLogger(__name__)


def _play_beep_sync(frequency: int = 1000, duration_ms: int = 250) -> None:
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(frequency, duration_ms)
        else:
            # Fallback for Linux / macOS via terminal bell or sounddevice
            print("\a", end="", flush=True)
    except Exception as e:
        logger.debug("Beep playback exception: %s", e)


def trigger_distraction_beep(frequency: int = 1000, duration_ms: int = 250) -> None:
    """Trigger an audible distraction beep asynchronously without blocking video processing."""
    if not config.ENABLE_AUDIO_BEEP:
        return

    thread = threading.Thread(
        target=_play_beep_sync,
        args=(frequency, duration_ms),
        daemon=True,
    )
    thread.start()
