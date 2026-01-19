#!/usr/bin/env python3
import os
import time
import socket
import subprocess
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


def resolve(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return None


def ping_once(host: str, timeout_s: int = 1) -> tuple[bool, str]:
    """
    Ping 1 paquet, retourne (ok, résumé).
    Linux: ping -c 1 -W <timeout>
    """
    try:
        p = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_s), host],
            capture_output=True,
            text=True,
        )
        ok = (p.returncode == 0)
        # Résumé lisible
        out = (p.stdout + "\n" + p.stderr).strip()
        # On réduit la sortie à une ligne utile
        line = ""
        for l in out.splitlines():
            if "bytes from" in l or "Destination Host Unreachable" in l or "100% packet loss" in l:
                line = l
                break
        if not line:
            # fallback: dernière ligne stats
            line = out.splitlines()[-1] if out else "no output"
        return ok, line
    except Exception as e:
        return False, f"ping error: {e}"


def http_get(url: str, timeout_s: float = 2.0) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(url)
        if r.status_code == 200:
            # on log un extrait court
            body = r.text.strip().replace("\n", "")[:200]
            return True, f"HTTP 200 {body}"
        return False, f"HTTP {r.status_code} {r.text.strip()[:200]}"
    except Exception as e:
        return False, f"http error: {repr(e)}"


def main():
    # charge .env si présent
    load_dotenv()

    sensor_url = os.getenv("CUVE_SENSOR_URL")
    if not sensor_url:
        print("ERROR: CUVE_SENSOR_URL non défini (dans .env ou env).")
        print("Ex: CUVE_SENSOR_URL=http://cuve.local.mondomaine.org/distance")
        raise SystemExit(2)

    interval_s = int(os.getenv("CUVE_MONITOR_INTERVAL_SECONDS", "60"))
    ping_timeout_s = int(os.getenv("CUVE_PING_TIMEOUT_SECONDS", "1"))
    http_timeout_s = float(os.getenv("CUVE_HTTP_TIMEOUT_SECONDS", "2.0"))

    parsed = urlparse(sensor_url)
    hostname = parsed.hostname
    if not hostname:
        print(f"ERROR: URL invalide: {sensor_url}")
        raise SystemExit(2)

    log_path = os.getenv("CUVE_MONITOR_LOG", "cuve_monitor.log")

    print(f"Monitoring CUVE_SENSOR_URL={sensor_url}")
    print(f"Host={hostname} | interval={interval_s}s | log={log_path}")
    print("CTRL+C pour arrêter.\n")

    while True:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ip = resolve(hostname)
        ip_txt = ip if ip else "DNS_FAIL"

        ping_ok, ping_msg = ping_once(ip or hostname, timeout_s=ping_timeout_s)
        http_ok, http_msg = http_get(sensor_url, timeout_s=http_timeout_s)

        status = "OK" if (ping_ok and http_ok) else ("PING_ONLY" if ping_ok else ("HTTP_ONLY" if http_ok else "DOWN"))

        line = f"{ts} | {status:<8} | host={hostname} ip={ip_txt} | ping={ping_ok} '{ping_msg}' | http={http_ok} '{http_msg}'"
        print(line)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        time.sleep(interval_s)


if __name__ == "__main__":
    main()
