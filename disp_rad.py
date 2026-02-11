import psutil
from datetime import datetime
import time
import subprocess
import logging
import sys
import re

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import ImageFont

# ============================================================================
# INITIALIZATION & HARDWARE
# ============================================================================
device = None
oled_available = False
try:
    serial = i2c(port=1, address=0x3C)
    device = sh1106(serial, rotate=0)
    oled_available = True
except Exception:
    pass

try:
    from gpiozero import LED
except ImportError:
    class LED:
        def __init__(self, pin): pass
        def on(self): pass
        def off(self): pass

green_led, yellow_led, red_led = LED(22), LED(27), LED(17)

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf", 12)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf", 10)
except:
    font = ImageFont.load_default()
    small_font = ImageFont.load_default()

# ============================================================================
# SCIENTIFIC DATA ACQUISITION
# ============================================================================

def get_network_stats():
    stats = {'ssid': "Offline", 'dbm': -100, 'gw': None, 'ip': "No IP"}
    try:
        iw = subprocess.check_output(['iwconfig', 'wlan0'], stderr=subprocess.STDOUT).decode('utf-8')
        ssid_m = re.search(r'ESSID:"([^"]+)"', iw)
        dbm_m = re.search(r'Signal level=(-\d+)', iw)
        if ssid_m: stats['ssid'] = ssid_m.group(1)
        if dbm_m: stats['dbm'] = int(dbm_m.group(1))
        
        stats['gw'] = subprocess.check_output("ip route show 0.0.0.0/0 | awk '{print $3}'", shell=True).decode('utf-8').strip()
        stats['ip'] = subprocess.check_output("hostname -I | cut -d' ' -f1", shell=True).decode("utf-8").strip()
    except: pass
    return stats

# ============================================================================
# THE UI ENGINE
# ============================================================================

def draw_ui_elements(draw, s, timestamp, frame):
    """Full UI Encapsulation: 2-letter DOW, 1-letter Meridian, Max Clearance."""
    
    # 1. OUTER BORDER
    draw.rectangle((0, 0, 127, 63), outline=255, fill=0)

    # 2. HEADER SECTION (Centering: y=2)
    draw.text((4, 2), timestamp, font=font, fill=255)
    
    # Signal Bars (Upper Right, Aligned to y=4)
    x_bars, y_bars = 110, 4
    bars = 0
    if s['dbm'] > -50: bars = 4
    elif s['dbm'] > -60: bars = 3
    elif s['dbm'] > -70: bars = 2
    elif s['dbm'] > -80: bars = 1

    for i in range(4):
        bx = x_bars + (i * 4)
        by_top = y_bars + 10 - (i * 2 + 2)
        by_bot = y_bars + 10
        fill = 255 if i < bars else 0
        draw.rectangle((bx, by_top, bx + 2, by_bot), outline=255, fill=fill)

    # Blinking Alert Icon (Triangle !)
    if not s['gw'] and s['dbm'] > -100 and (frame % 2 == 0):
        ax, ay = 96, 4
        draw.polygon([(ax, ay+10), (ax+5, ay), (ax+10, ay+10)], outline=255, fill=0)
        draw.line((ax+5, ay+3, ax+5, ay+7), fill=255)
        draw.point((ax+5, ay+9), fill=255)

    # INTERNAL SEPARATOR (y=17 for breathing room)
    draw.line((1, 17, 126, 17), fill=255)

    # 3. DATA SECTION (X-padding = 4px)
    draw.text((4, 21), f"IP: {s['ip']}", font=font, fill=255)
    draw.text((4, 34), f"GW: {s['gw'] if s['gw'] else 'MISSING'}", font=font, fill=255)
    
    # Bottom Row: Lifted to y=47 for border clearance
    draw.text((4, 47), f"Net: {s['ssid'][:11]}", font=font, fill=255)
    draw.text((92, 49), f"{s['dbm']}dBm", font=small_font, fill=255)

    # HEARTBEAT (Bottom Right)
    if frame % 2 == 0:
        draw.point((125, 61), fill=255)

# ============================================================================
# MAIN LOOP
# ============================================================================

frame_counter = 0

try:
    while True:
        stats = get_network_stats()
        
        # Build 2-letter DOW and 1-letter Meridian: Tu Feb 10 10:29P
        now = datetime.now()
        dow = now.strftime("%a")[:2] 
        rest = now.strftime("%b %-d %-I:%M")
        meridian = now.strftime("%p")[0]
        t_str = f"{dow} {rest}{meridian}" 

        if oled_available:
            with canvas(device) as draw:
                draw_ui_elements(draw, stats, t_str, frame_counter)

        # LED & Network Recovery
        if stats['dbm'] > -100 and stats['gw']:
            green_led.on(); yellow_led.off(); red_led.off()
        elif stats['dbm'] > -100 and not stats['gw']:
            green_led.off(); yellow_led.on(); red_led.off()
        else:
            green_led.off(); yellow_led.off(); red_led.on()
            subprocess.run(["nmcli", "device", "reapply", "wlan0"], capture_output=True)

        frame_counter += 1
        time.sleep(1)

except KeyboardInterrupt:
    pass
finally:
    [l.off() for l in [green_led, yellow_led, red_led] if hasattr(l, 'off')]

