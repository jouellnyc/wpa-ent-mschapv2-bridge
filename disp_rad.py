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

# Optional GPIO LED support
try:
    from gpiozero import LED
    gpio_available = True
except Exception:
    gpio_available = False
    class LED:
        def __init__(self, pin): self.pin = pin
        def on(self): pass
        def off(self): pass
        def blink(self, on_time=0.5, off_time=0.5, background=True): pass
        def close(self): pass

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

file_handler = logging.FileHandler('/tmp/wifi_monitor.log', mode='a')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ============================================================================
# CONFIGURATION
# ============================================================================
start = 2
font_size = 12
# Ensure this path is correct for your OS; common alternative: /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
font_path = "/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf" 
try:
    font = ImageFont.truetype(font_path, font_size)
except:
    font = ImageFont.load_default()

GREEN_PIN, YELLOW_PIN, RED_PIN = 22, 27, 17

# ============================================================================
# HARDWARE INITIALIZATION
# ============================================================================
device = None
oled_available = False
try:
    serial = i2c(port=1, address=0x3C)
    device = sh1106(serial, rotate=0)
    oled_available = True
    logger.info("✓ OLED initialized")
except Exception as e:
    logger.warning(f"OLED not available: {e}")

green_led = LED(GREEN_PIN)
yellow_led = LED(YELLOW_PIN)
red_led = LED(RED_PIN)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_wifi_details():
    """Dynamically fetch SSID and Signal Strength using iwconfig."""
    ssid, dbm = "Offline", "--"
    try:
        # We use iwconfig because it's faster for signal levels than scanning
        output = subprocess.check_output(['iwconfig', 'wlan0'], stderr=subprocess.STDOUT).decode('utf-8')
        
        # Extract SSID
        ssid_match = re.search(r'ESSID:"([^"]+)"', output)
        if ssid_match:
            ssid = ssid_match.group(1)
        
        # Extract Signal Level (dBm)
        dbm_match = re.search(r'Signal level=(-\d+)', output)
        if dbm_match:
            dbm = f"{dbm_match.group(1)}dBm"
            
    except Exception as e:
        logger.debug(f"Error fetching WiFi details: {e}")
    
    return ssid, dbm

def set_led_state(state):
    try:
        if state == 'success':
            yellow_led.off(); red_led.off(); green_led.on()
        elif state == 'failure':
            yellow_led.off(); green_led.off(); red_led.on()
        elif state == 'reconfiguring':
            green_led.off(); red_led.off(); yellow_led.blink(0.6, 0.6)
    except: pass

def show_display(IP, auth_msg, wifi_msg, ctime, ssid, dbm):
    if not oled_available: return
    try:
        with canvas(device) as draw:
            draw.text((0, start), ctime, font=font, fill=255)
            draw.text((0, start+15), f"IP: {IP}", font=font, fill=255)
            draw.text((0, start+30), f"GW: {auth_msg}", font=font, fill=255)
            # Line 4: SSID and Signal Strength
            draw.text((0, start+45), f"{ssid[:12]} {dbm}", font=font, fill=255)
    except Exception as e:
        logger.error(f"Display error: {e}")

# ============================================================================
# MAIN LOOP
# ============================================================================
logger.info("WiFi Monitor Starting (Dynamic Mode)")

try:
    while True:
        ctime = datetime.now().strftime("%b-%d %I:%M %p")
        current_ssid, signal_dbm = get_wifi_details()
        
        # Use your custom logic to find IP
        try:
            IP = subprocess.check_output("hostname -I | cut -d' ' -f1", shell=True).decode("utf-8").strip()
            if not IP: IP = '127.0.0.1'
        except: IP = 'NA'

        # Fetch Gateway dynamically (no lemmings allowed)
        try:
            gw_cmd = "ip route | grep default | awk '{print $3}'"
            gateway = subprocess.check_output(gw_cmd, shell=True).decode("utf-8").strip()
            if not gateway: gateway = 'None'
        except: gateway = 'Error'

        if current_ssid != "Offline":
            set_led_state('success')
            show_display(IP, gateway, "Online", ctime, current_ssid, signal_dbm)
        else:
            set_led_state('reconfiguring')
            show_display(IP, "---", "Searching", ctime, "SCANNING...", "--")
            # Only trigger reconfigure if we've actually lost the carrier
            subprocess.run(["/usr/sbin/wpa_cli", "-i", "wlan0", "reconfigure"], capture_output=True)
            time.sleep(10)

        # Sleep for 60s - keeps clock relatively accurate without hammering the CPU
        time.sleep(60)

except KeyboardInterrupt:
    green_led.off(); yellow_led.off(); red_led.off()
    logger.info("Shutdown requested.")
