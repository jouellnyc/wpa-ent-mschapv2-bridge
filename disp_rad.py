
import psutil
from datetime import datetime

import time
import subprocess
import logging

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import ImageFont

serial = i2c(port=1, address=0x3C)
device = sh1106(serial, rotate=0)

#This is the SSID to look for
ESSID="SSID"
#This is the SSID to report on the OLED
ESSIDT="SSID"

logging.basicConfig(level=logging.DEBUG, filename='/tmp/wifi.exception.log', filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s')

start=2
font_size = 12 

font_path = "/usr/share/fonts/truetype/piboto/PibotoLt-Regular.ttf"
font = ImageFont.truetype(font_path, font_size)

def show_display(IP, auth_msg, wifi_msg,ctime): 
    with canvas(device) as draw:
        draw.text((0, start), ctime, font=font,  fill=255)
        draw.text((0, start+15), f"IP: {IP}", font=font,fill=255)
        draw.text((0, start+30), f"AUTH: {auth_msg}",  font=font, fill=255)
        draw.text((0, start+45), f"SSID: {ESSIDT} {wifi_msg}",  font=font, fill=255)

def write_proc(err_out, ctime):
    try:
        with open('/boot/pwifi.restart.log','a') as df:
            df.write(f"{ctime}: {err_out}")
    except Exception as e:
        logging.exception("write_proc() failed: {e}")

def is_connected_to_wifi():
    try:
        result = subprocess.check_output(['iwconfig']).decode('utf-8')
        if ESSID in result:
            return True
        else:
            return False
    except subprocess.CalledProcessError:
        return False


while True:

    ctime = datetime.now().strftime("%b-%d-%y %I:%M %p")
    cmd = ["/usr/local/sbin/wpa_cli", "-i", "wlan0", "reconfigure"]

    IP       = 'NA'
    wifi_msg = 'NA'  
    auth_msg = 'NA'

    try:
        #Appears to always/mostly return 0 
        result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    except subprocess.CalledProcessError as e:
        auth_msg = str(e)
        logging.exception("Subprocess Called Process Error: {e}")
    except Exception as e:
        auth_msg = str(e)
        logging.exception(f"Non Specific Exception: {e}")
    else:
        output_and_error = result.stdout + result.stderr
        write_proc(output_and_error, ctime)
        #cmd usually takes about 15 seconds or so
        time.sleep(17)
        if is_connected_to_wifi():
            auth_msg='OK'
            wifi_msg="Online"
            IP  = subprocess.check_output("hostname -I | cut -d' ' -f1", shell=True).decode("utf-8")
        else:
            auth_msg='Unknown'
            wifi_msg="Offline"
    finally:
        show_display(IP, auth_msg, wifi_msg, ctime)
    time.sleep(285)

