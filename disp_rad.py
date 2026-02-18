
import psutil
from datetime import datetime
import time
import subprocess
import logging
import re
import itertools

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import ImageFont

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Signal strength thresholds (dBm)
SIGNAL_EXCELLENT = -50
SIGNAL_GOOD      = -60
SIGNAL_FAIR      = -70
SIGNAL_POOR      = -80
SIGNAL_NONE      = -100

# Display coordinates
BARS_X, BARS_Y       = 110, 4
ALERT_X, ALERT_Y     = 96, 4
HEARTBEAT_X          = 125
HEARTBEAT_Y          = 61
SEPARATOR_Y          = 17
SSID_MAX_CHARS       = 11

# ============================================================================
# HARDWARE INITIALIZATION
# ============================================================================

device = None
oled_available = False
try:
    serial = i2c(port=1, address=0x3C)
    device = sh1106(serial, rotate=0)
    oled_available = True
    log.info("OLED display initialized.")
except Exception as e:
    log.warning(f"OLED unavailable: {e}")

try:
    from gpiozero import LED
except ImportError:
    log.warning("gpiozero not found; using LED stub.")
    from unittest.mock import MagicMock
    LED = lambda pin: MagicMock()

green_led  = LED(22)
yellow_led = LED(27)
red_led    = LED(17)

try:
    font       = ImageFont.truetype("/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf", 12)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf", 10)
except Exception as e:
    log.warning(f"Custom font unavailable, using default: {e}")
    font       = ImageFont.load_default()
    small_font = ImageFont.load_default()

# ============================================================================
# NETWORK DATA ACQUISITION
# ============================================================================

def _run(cmd, **kwargs):
    """Safe subprocess wrapper; returns stdout string or None on failure."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, **kwargs).decode("utf-8").strip()
    except Exception as e:
        log.debug(f"Subprocess error ({cmd}): {e}")
        return None


def get_network_stats():
    stats = {"ssid": "Offline", "dbm": SIGNAL_NONE, "gw": None, "ip": "No IP"}

    # Wi-Fi info via iwconfig
    iw_output = _run(["iwconfig", "wlan0"])
    if iw_output:
        ssid_m = re.search(r'ESSID:"([^"]+)"', iw_output)
        dbm_m  = re.search(r"Signal level=(-\d+)", iw_output)
        if ssid_m:
            stats["ssid"] = ssid_m.group(1)
        if dbm_m:
            stats["dbm"] = int(dbm_m.group(1))

    # Default gateway — avoid shell=True by parsing in Python
    route_output = _run(["ip", "route", "show", "0.0.0.0/0"])
    if route_output:
        parts = route_output.split()
        # "default via <gw> dev ..."
        if "via" in parts:
            stats["gw"] = parts[parts.index("via") + 1]

    # Local IP
    ip_output = _run(["hostname", "-I"])
    if ip_output:
        stats["ip"] = ip_output.split()[0]

    return stats

# ============================================================================
# UI ENGINE
# ============================================================================

def _dbm_to_bars(dbm):
    if dbm > SIGNAL_EXCELLENT: return 4
    if dbm > SIGNAL_GOOD:      return 3
    if dbm > SIGNAL_FAIR:      return 2
    if dbm > SIGNAL_POOR:      return 1
    return 0


def _draw_header(draw, timestamp, stats, frame):
    draw.text((4, 2), timestamp, font=font, fill=255)
    _draw_signal_bars(draw, stats["dbm"])
    _draw_alert_icon(draw, stats, frame)


def _draw_signal_bars(draw, dbm):
    bars = _dbm_to_bars(dbm)
    for i in range(4):
        bx     = BARS_X + (i * 4)
        by_top = BARS_Y + 10 - (i * 2 + 2)
        by_bot = BARS_Y + 10
        fill   = 255 if i < bars else 0
        draw.rectangle((bx, by_top, bx + 2, by_bot), outline=255, fill=fill)


def _draw_alert_icon(draw, stats, frame):
    """Blink a triangle '!' when connected but gateway is missing."""
    if stats["gw"] or stats["dbm"] <= SIGNAL_NONE:
        return
    if frame % 2 == 0:
        ax, ay = ALERT_X, ALERT_Y
        draw.polygon([(ax, ay + 10), (ax + 5, ay), (ax + 10, ay + 10)], outline=255, fill=0)
        draw.line([(ax + 5, ay + 3), (ax + 5, ay + 7)], fill=255)
        draw.point((ax + 5, ay + 9), fill=255)


def _draw_body(draw, stats):
    draw.text((4, 21), f"IP:  {stats['ip']}",                              font=font, fill=255)
    draw.text((4, 34), f"GW:  {stats['gw'] if stats['gw'] else 'MISSING'}", font=font, fill=255)
    draw.text((4, 47), f"Net: {stats['ssid'][:SSID_MAX_CHARS]}",            font=font, fill=255)
    draw.text((92, 49), f"{stats['dbm']}dBm",                               font=small_font, fill=255)


def draw_ui_elements(draw, stats, timestamp, frame):
    # Outer border
    draw.rectangle((0, 0, 127, 63), outline=255, fill=0)
    # Separator
    draw.line((1, SEPARATOR_Y, 126, SEPARATOR_Y), fill=255)
    # Header
    _draw_header(draw, timestamp, stats, frame)
    # Body
    _draw_body(draw, stats)
    # Heartbeat dot
    if frame % 2 == 0:
        draw.point((HEARTBEAT_X, HEARTBEAT_Y), fill=255)

# ============================================================================
# LED STATE
# ============================================================================

def update_leds(stats):
    connected   = stats["dbm"] > SIGNAL_NONE
    has_gateway = bool(stats["gw"])

    green_led.off(); yellow_led.off(); red_led.off()

    if connected and has_gateway:
        green_led.on()
    elif connected:
        yellow_led.on()
    else:
        red_led.on()
        log.info("No Wi-Fi signal — attempting reapply.")
        subprocess.run(["nmcli", "device", "reapply", "wlan0"], capture_output=True)

# ============================================================================
# MAIN LOOP
# ============================================================================

def build_timestamp():
    now      = datetime.now()
    dow      = now.strftime("%a")[:2]
    rest     = now.strftime("%b %-d %-I:%M")
    meridian = now.strftime("%p")[0]
    return f"{dow} {rest}{meridian}"


def main():
    log.info("Network monitor starting.")
    next_tick = time.monotonic()

    try:
        for frame in itertools.count():
            stats     = get_network_stats()
            timestamp = build_timestamp()

            if oled_available:
                with canvas(device) as draw:
                    draw_ui_elements(draw, stats, timestamp, frame)

            update_leds(stats)

            # Drift-free 1-second cadence
            next_tick += 1.0
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

    except KeyboardInterrupt:
        log.info("Shutting down.")
    finally:
        for led in [green_led, yellow_led, red_led]:
            try:
                led.off()
            except Exception as e:
                log.warning(f"Failed to turn off LED: {e}")
        if oled_available and device:
            try:
                device.cleanup()
            except Exception as e:
                log.warning(f"Failed to clean up OLED device: {e}")


if __name__ == "__main__":
    main()

