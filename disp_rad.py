
import psutil
from datetime import datetime
import time
import subprocess
import logging
import sys

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import ImageFont

# Optional GPIO LED support (Raspberry Pi)
# If gpiozero is not available this falls back to a dummy LED that just logs calls.
try:
    from gpiozero import LED
    gpio_available = True
except Exception:
    gpio_available = False
    class LED:
        def __init__(self, pin):
            self.pin = pin
        def on(self):
            logging.debug(f"GPIO not available: pretend LED {self.pin} ON")
        def off(self):
            logging.debug(f"GPIO not available: pretend LED {self.pin} OFF")
        def blink(self, on_time=0.5, off_time=0.5, background=True):
            logging.debug(f"GPIO not available: pretend LED {self.pin} BLINK")
        def close(self):
            pass

# ============================================================================
# LOGGING CONFIGURATION - Best Practices
# ============================================================================

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create formatters
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

simple_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# File handler for all logs (DEBUG and above)
file_handler = logging.FileHandler('/tmp/wifi_monitor.log', mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(detailed_formatter)

# File handler for errors only
error_handler = logging.FileHandler('/tmp/wifi_monitor_errors.log', mode='a')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(detailed_formatter)

# Console handler for INFO and above
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(simple_formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(error_handler)
logger.addHandler(console_handler)

# ============================================================================
# CONFIGURATION
# ============================================================================

# This is the SSID to look for
ESSID = "SSID"
# This is the SSID to report on the OLED
ESSIDT = "SSID"

start = 2
font_size = 12

font_path = "/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf"
font = ImageFont.truetype(font_path, font_size)

# LED pin configuration
GREEN_PIN = 22 
YELLOW_PIN = 27
RED_PIN = 17 


# ============================================================================
# INITIALIZATION
# ============================================================================

logger.info("=" * 80)
logger.info("WiFi Monitor Script Starting")
logger.info(f"GPIO Available: {gpio_available}")
logger.info(f"Monitoring SSID: {ESSID}")
logger.info(f"LED Pins - Green: {GREEN_PIN}, Yellow: {YELLOW_PIN}, Red: {RED_PIN}")
logger.info("=" * 80)

# Try to initialize OLED display - but don't fail if it's not available
device = None
oled_available = False
try:
    serial = i2c(port=1, address=0x3C)
    device = sh1106(serial, rotate=0)
    oled_available = True
    logger.info("✓ OLED display initialized successfully")
except Exception as e:
    logger.warning(f"OLED display not available: {e}")
    logger.warning("Continuing with LED-only mode...")
    logger.info("Run oled_diagnostic.py to troubleshoot the display")
    oled_available = False

green_led = LED(GREEN_PIN)
yellow_led = LED(YELLOW_PIN)
red_led = LED(RED_PIN)
logger.info("LED objects created successfully")

# ============================================================================
# FUNCTIONS
# ============================================================================

def leds_all_off():
    """Turn all LEDs off."""
    try:
        green_led.off()
        yellow_led.off()
        red_led.off()
        logger.debug("All LEDs turned off")
    except Exception as e:
        logger.error(f"Failed to turn LEDs off: {e}", exc_info=True)

def set_led_state(state):
    """
    Set LED state based on system status.
    
    Args:
        state: one of 'success', 'failure', 'unknown', 'reconfiguring'
    """
    logger.debug(f"Setting LED state to: {state}")
    try:
        if state == 'success':
            yellow_led.off()
            red_led.off()
            green_led.on()
            logger.info("LED State: SUCCESS (green on)")
        elif state == 'failure':
            yellow_led.off()
            green_led.off()
            red_led.on()
            logger.warning("LED State: FAILURE (red on)")
        elif state == 'unknown':
            green_led.off()
            red_led.off()
            yellow_led.on()
            logger.info("LED State: UNKNOWN (yellow on)")
        elif state == 'reconfiguring':
            green_led.off()
            red_led.off()
            yellow_led.blink(on_time=0.6, off_time=0.6, background=True)
            logger.info("LED State: RECONFIGURING (yellow blinking)")
        else:
            leds_all_off()
            logger.warning(f"Unknown LED state requested: {state}, turning all off")
    except Exception as e:
        logger.error(f"Error setting LED state to {state}: {e}", exc_info=True)

def show_display(IP, auth_msg, wifi_msg, ctime):
    """Update OLED display with current status."""
    if not oled_available or device is None:
        logger.debug(f"OLED not available - Status: IP: {IP}, AUTH: {auth_msg}, WiFi: {wifi_msg}")
        return
        
    try:
        with canvas(device) as draw:
            draw.text((0, start), ctime, font=font, fill=255)
            draw.text((0, start+15), f"IP: {IP}", font=font, fill=255)
            draw.text((0, start+30), f"AUTH: {auth_msg}", font=font, fill=255)
            draw.text((0, start+45), f"SSID: {ESSIDT} {wifi_msg}", font=font, fill=255)
        logger.debug(f"Display updated - IP: {IP}, AUTH: {auth_msg}, WiFi: {wifi_msg}")
    except Exception as e:
        logger.error(f"Failed to update display: {e}", exc_info=True)

def write_proc(err_out, ctime):
    """Write process output to restart log."""
    try:
        with open('/boot/pwifi.restart.log', 'a') as df:
            df.write(f"{ctime}: {err_out}\n")
        logger.debug(f"Wrote to restart log at {ctime}")
    except Exception as e:
        logger.error(f"write_proc() failed: {e}", exc_info=True)

def is_connected_to_wifi():
    """Check if connected to the configured WiFi network."""
    try:
        result = subprocess.check_output(['iwconfig'], stderr=subprocess.STDOUT).decode('utf-8')
        connected = ESSID in result
        logger.debug(f"WiFi connection check: {'Connected' if connected else 'Disconnected'}")
        return connected
    except subprocess.CalledProcessError as e:
        logger.error(f"iwconfig command failed: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking WiFi connection: {e}", exc_info=True)
        return False

# ============================================================================
# MAIN LOOP
# ============================================================================

leds_all_off()
loop_count = 0

try:
    logger.info("Entering main monitoring loop")
    
    while True:
        loop_count += 1
        logger.info(f"--- Loop iteration {loop_count} started ---")
        
        ctime = datetime.now().strftime("%b-%d-%y %I:%M %p")
        cmd = ["/usr/sbin/wpa_cli", "-i", "wlan0", "reconfigure"]

        IP = 'NA'
        wifi_msg = 'NA'
        auth_msg = 'NA'

        try:
            # Indicate we're reconfiguring
            logger.info("Initiating WiFi reconfiguration")
            set_led_state('reconfiguring')
            
            # Show "reconfiguring" status on OLED immediately
            show_display(IP, "Reconfiguring...", "Checking...", ctime)
            
            # Run wpa_cli reconfigure
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=30)
            logger.debug(f"Command exit code: {result.returncode}")
            
        except subprocess.TimeoutExpired as e:
            auth_msg = "Timeout"
            wifi_msg = "Error"
            logger.error(f"wpa_cli command timed out after 30 seconds: {e}")
            set_led_state('failure')
            show_display(IP, auth_msg, wifi_msg, ctime)
            
        except subprocess.CalledProcessError as e:
            auth_msg = str(e)
            wifi_msg = "Error"
            logger.error(f"Subprocess CalledProcessError: {e}", exc_info=True)
            set_led_state('failure')
            show_display(IP, auth_msg, wifi_msg, ctime)
            
        except Exception as e:
            auth_msg = str(e)
            wifi_msg = "Error"
            logger.error(f"Unexpected exception during reconfigure: {e}", exc_info=True)
            set_led_state('failure')
            show_display(IP, auth_msg, wifi_msg, ctime)
            
        else:
            output_and_error = result.stdout + result.stderr
            if output_and_error.strip():
                logger.debug(f"wpa_cli output: {output_and_error.strip()}")
            write_proc(output_and_error, ctime)
            
            # Wait for WiFi to stabilize
            logger.info("Waiting 17 seconds for WiFi to stabilize...")
            
            # Update display during wait to show we're still working
            show_display(IP, "Stabilizing...", "Please wait...", ctime)
            time.sleep(17)
            
            # Check connection status
            if is_connected_to_wifi():
                auth_msg = 'OK'
                wifi_msg = "Online"
                try:
                    IP = subprocess.check_output("hostname -I | cut -d' ' -f1", shell=True).decode("utf-8").strip()
                    logger.info(f"WiFi connected successfully - IP: {IP}")
                except Exception as e:
                    IP = 'Error'
                    logger.error(f"Failed to get IP address: {e}", exc_info=True)
                set_led_state('success')
                show_display(IP, auth_msg, wifi_msg, ctime)
            else:
                auth_msg = 'Unknown'
                wifi_msg = "Offline"
                logger.warning("WiFi connection failed - no connection detected")
                set_led_state('failure')
                show_display(IP, auth_msg, wifi_msg, ctime)
                
        finally:
            # Log final status
            logger.info(f"Status - IP: {IP}, Auth: {auth_msg}, WiFi: {wifi_msg}")

        # Sleep between runs (approx 4m45s)
        logger.info(f"Loop iteration {loop_count} complete. Sleeping for 285 seconds...")
        time.sleep(285)

except KeyboardInterrupt:
    logger.info("Interrupted by user (Ctrl+C) - cleaning up LEDs")
    leds_all_off()
    try:
        green_led.close()
        yellow_led.close()
        red_led.close()
        logger.info("LED cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during LED cleanup: {e}", exc_info=True)
        
except Exception as e:
    logger.critical(f"Unhandled exception in main loop: {e}", exc_info=True)
    leds_all_off()
    try:
        green_led.close()
        yellow_led.close()
        red_led.close()
    except Exception as cleanup_error:
        logger.error(f"Error during emergency LED cleanup: {cleanup_error}", exc_info=True)
    raise

finally:
    logger.info("WiFi Monitor Script shutting down")
    logger.info("=" * 80)
