import asyncio
import fcntl
import re
import socket
import struct
import time

_internet_cache = {"last_check": 0, "status": False}


def ip_address(ifname="wlan0"):
    """
    Return the IP address for given interface
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            ip_addr = socket.inet_ntoa(
                fcntl.ioctl(
                    s.fileno(),
                    0x8915,  # SIOCGIFADDR
                    struct.pack("256s", bytes(ifname[:15], "utf-8")),
                )[20:24]
            )
            matchObj = re.match(r"169\.254", ip_addr)
            if matchObj:
                # ignore self-assigned link-local address
                return None
            else:
                return ip_addr
    except OSError:
        return None


async def internet_connection():
    """
    Return True if connected to Internet, False otherwise
    """
    now = time.time()
    # Cache result for 5 minutes to avoid redundant network I/O
    if now - _internet_cache["last_check"] < 300:
        return _internet_cache["status"]

    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _do_internet_connection)
    
    _internet_cache["last_check"] = now
    _internet_cache["status"] = status
    return status


def _do_internet_connection():
    DNS_SERVER_LIST = [
        "1.1.1.1",  # Cloudflare
        "8.8.8.8",  # Google DNS
    ]
    dns_port = 53
    timeout = 2.0
    for dns_server in DNS_SERVER_LIST:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((dns_server, dns_port))
                return True
        except OSError:
            pass
    return False
