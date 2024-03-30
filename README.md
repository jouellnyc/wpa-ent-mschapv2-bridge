# WPA2-Enterprise-Bridge
Raspberry Pi WPA2-Enterprise microcontroller "Bridge" 

# Why? 

1 - Esp32s and Raspberry pi picos cannot access networks with WPA-Enterprise authentication.

2 - Wifi "Monitor" on your desk. As an SRE/Staff Engineer, I find it a nice ice breaker, talking point:

![Pi Oled](images/pi-oled.png)

# Upfront

| Requirements |
|-----------------|
|A raspbery pi of some sort - I used a pi zero w|
|A second USB [wireless adapter](https://www.amazon.com/gp/product/B07C9TYDR4) - I used a Panda as "wlan1" for the AP|
|Possibly a USB OTG hub|
|Proper power for the Pi - I use a 1.5A 5V unit with a barrel plug adapter (for easy release / attach)|
|Optional - [OLED](https://www.amazon.com/gp/product/B08KY21SR2/) - I used 0.96" OLED on a tiny breadboard|

| Cautionary Notes | Description                                             |
|-----------------|---------------------------------------------------------|
| 1. | May need to use a low security workaround for ssl ciphers| 
| 2. | Your password is in clear text protected  by unix permissions (unless your pi is stolen)|
| 3. | Your Network Admin may not like this - I am just playing around using a LAB - use caution!|

| Other Notes | Description                                             |
|-----------------|---------------------------------------------------------|
| 1. | This works Rasberry Pi OS Version "10 (buster)" (Bookworm in the future) |
| 2. | Expecation is the microcontroller is capable of 2.4 GHZ only|
| 3. | There is no actual network bridging happening per se, it's just a fancy term I use |

With all that out of the way...

# How To on Raspberry Pi OS Bullseye and older

1. Install Buster per usual
2. Install Hostapd - I used Hostapd v2.8-devel
3. Install Dnsmasq - I used Dnsmasq version 2.80  
4. I used wpa_supplicant v2.10
5. Setup your config files like this or similar:


```
1 - /etc/wpa_supplicant/wpa_supplicant.conf

country=US
ctrl_interface=/var/run/wpa_supplicant
ap_scan=1
update_config=1
### Not Secure or wise for Production 
#tls_disable_tlsv1_0=0
#tls_disable_tlsv1_1=0
#openssl_ciphers=DEFAULT@SECLEVEL=0

network={

    ssid="YOURSID"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="YOURID"

}


cred={

    password="YOURPASS"
    domain="DNS_SUBJECT_NAME_IN_THE_RADIUS_SERVERS_CERT"
    phase2="auth=MSCHAPV2"

}

2 - /etc/systemd/system/multi-user.target.wants/wpa_supplicant.service  (this should be the same, provided for convenience)

[Unit]
Description=WPA supplicant
Before=network.target
After=dbus.service
Wants=network.target

[Service]
Type=dbus
BusName=fi.w1.wpa_supplicant1
ExecStart=/sbin/wpa_supplicant -u -s -O /run/wpa_supplicant

[Install]
WantedBy=multi-user.target
Alias=dbus-fi.w1.wpa_supplicant1.service




3 - /etc/dnsmasq.conf 

# Set the interface to listen on
interface=wlan1

# Specify the range of IP addresses to lease
dhcp-range=192.168.1.175,192.168.1.177,12h

# Set the default gateway
dhcp-option=3,192.168.1.100

# Set the DNS server(s)
dhcp-option=6,8.8.8.8,8.8.4.4

# Set the domain name
domain=lan

# Set the local hostname
expand-hosts

# Log DHCP requests
log-dhcp

# Log to syslog
log-facility=/var/log/dnsmasq.log


4 - /etc/systemd/system/multi-user.target.wants/hostapd.service 
[Unit]
Description=Advanced IEEE 802.11 AP and IEEE 802.1X/WPA/WPA2/EAP Authenticator
After=network.target

[Service]
Type=forking
PIDFile=/run/hostapd.pid
Restart=on-failure
RestartSec=2
Environment=DAEMON_CONF=/etc/hostapd/hostapd_24.conf
EnvironmentFile=-/etc/default/hostapd
ExecStart=/usr/sbin/hostapd  -B -t -f /var/log/hostapd.log ${DAEMON_CONF}
ExecStartPre=/bin/sleep 30 

[Install]
WantedBy=multi-user.target
#!/bin/bash


5 - /etc/hostapd/hostapd_24.conf

interface=wlan1
driver=nl80211
ssid=SOMESSID
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
ht_capab=[HT40+]
auth_algs=1
wpa=2
wpa_passphrase=SOMEPASSPHRASE
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP

6 - /etc/dhcpcd.conf

hostname
persistent
option rapid_commit
option domain_name_servers, domain_name, domain_search, host_name
option classless_static_routes
option interface_mtu
require dhcp_server_identifier
slaac private

# This is the default wireless adapter, gets a dynamic IP from the WPA2 Enterprise network 
interface wlan0
    dhcp

# This makes dhcpcd setup the interface but not run any wpa_supplicant hooks for wlan1,
# allowing the interface to get into AP mode 
# Further we will use the gateway of the interface using WPA-Enterprise
# Make sure the IP network numbers do not collide
interface wlan1
    static ip_address=192.168.1.100/24
    static routers=192.168.1.100
    static domain_name_servers=8.8.8.8 8.8.4.4
    nohook wpa_supplicant
    nogateway

7 - Make the Pi Route packets 
sysctl net.ipv4.ip_forward=1

8 - /etc/systemd/system/pi_screen_start.service 
[Unit]
Description=Pi Display OLED
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/root/pi_screen_start.sh

[Install]
WantedBy=multi-user.target

9 - /root/pi_screen_start.sh 
#!/bin/bash
/usr/bin/python3 /root/disp_rad.py

10 - disp_rad.py
See in this repo

```

6. Reboot

With that you should have:
- A functioning client wifi connection on WPA2-Enterprise on wlan0
- A functioning AP wifi connection on wlan1 that routes packets for the client


References

[Pi Forum solution for Hostapd Startup Failures](https://forums.raspberrypi.com/viewtopic.php?t=234145)

[Connection Bug lowering Security Levels](https://bugs.launchpad.net/ubuntu/+source/wpa/+bug/1958267)

[Connection Bug ](https://bbs.archlinux.org/viewtopic.php?id=286417&p=2)




# How To on Raspberry Pi OS 12/BookWorm
- Significantly shorter and easier, BUT alot has changed in BookWorm
- Change IP address,  pre shared key, SSID as you wish

```
nmcli con add con-name wlan1-AP ifname wlan1 type wifi ssid "YOURSSID"
nmcli con       modify wlan1-AP  wifi-sec.key-mgmt wpa-psk
nmcli con       modify wlan1-AP  wifi-sec.psk "12345678"
#NOTE: "bg" for 2.4GHz 802.11
nmcli con      modify wlan1-AP  802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
nmcli con      modify wlan1-AP  ipv4.method shared ipv4.address 192.168.7.1/24
```

References

[Turn Your Raspberry Pi into an Access Point (Bookworm ready) – RaspberryTips](https://raspberrytips.com/access-point-setup-raspberry-pi/#setting-up-an-access-point-on-raspberry-pi-os-bookworm)

[SOLVED -  How to create wifi AP (Access Point) with NetworkManager on Bookworm? - Raspberry Pi Forums](https://forums.raspberrypi.com/viewtopic.php?t=357998)


Finally, either route you took: Point your Microcontroller to your Pi as if it were an AP with a basic WPA2 passphrase (because now it is)




