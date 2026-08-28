#!/usr/bin/env python3
"""Street Banker Light Studio - local DMX bridge.

A browser cannot open a UDP socket, so it cannot speak Art-Net or sACN
directly. This is the missing 40 lines: it listens on localhost, and
forwards whatever the Light Studio sends it, byte for byte, to your
lighting network over UDP.

    python lx-bridge.py                     # Art-Net + sACN, port 7070
    python lx-bridge.py --port 7100
    python lx-bridge.py --artnet-host 192.168.1.55
    python lx-bridge.py --sacn-host 239.255.0.1

Then in the Light Studio choose "Art-Net node" or "sACN / E1.31" as the
output and set the same port. The page shows "bridge connected" when it
can reach this script.

Standard library only - no pip install, nothing to build. It never opens
a socket to the internet, only to the address you point it at, and it
never reads your audio or your show: the only thing it receives is a
finished DMX packet.

Why a plain HTTP POST rather than a WebSocket: browsers treat
http://127.0.0.1 as a trustworthy origin, so an HTTPS page is allowed to
reach it without a certificate, and a POST needs no framing code on
either side. At 30 frames a second on loopback the overhead is not
measurable.
"""
import argparse
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARTNET_PORT = 6454          # fixed by the Art-Net specification
SACN_PORT = 5568            # fixed by E1.31
MAX_FRAME = 2048            # a full universe packet is well under this

_state = {"artnet_host": "255.255.255.255", "sacn_host": "239.255.0.1",
          "frames": 0, "last": ""}


def _udp_socket(host):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if host.endswith(".255"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if host.startswith("239."):        # sACN multicast: keep it on this LAN
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    return s


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        # The Light Studio may be served from the app's own origin; allow it
        # to POST here. Only this loopback listener is exposed.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        """A health probe, so the page can say 'bridge connected'."""
        body = ('{"ok":true,"service":"street-banker-light-studio-bridge",'
                '"frames":%d,"artnet_host":"%s","sacn_host":"%s"}'
                % (_state["frames"], _state["artnet_host"], _state["sacn_host"])).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_FRAME:
            self.send_response(400)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        packet = self.rfile.read(length)
        path = self.path.split("?")[0].rstrip("/")
        try:
            if path == "/artnet":
                self.server.artnet.sendto(packet, (_state["artnet_host"], ARTNET_PORT))
            elif path == "/sacn":
                self.server.sacn.sendto(packet, (_state["sacn_host"], SACN_PORT))
            else:
                self.send_response(404)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            _state["frames"] += 1
        except OSError as exc:
            _state["last"] = str(exc)
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        """Silence the per-request log - this runs at 30 frames a second."""


def main():
    ap = argparse.ArgumentParser(description="Light Studio local DMX bridge")
    ap.add_argument("--port", type=int, default=7070,
                    help="localhost port the Light Studio posts to (default 7070)")
    ap.add_argument("--artnet-host", default="255.255.255.255",
                    help="Art-Net node address, or a broadcast address (default 255.255.255.255)")
    ap.add_argument("--sacn-host", default="239.255.0.1",
                    help="sACN destination; the default is the E1.31 multicast group for universe 1")
    args = ap.parse_args()

    _state["artnet_host"] = args.artnet_host
    _state["sacn_host"] = args.sacn_host

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.artnet = _udp_socket(args.artnet_host)
    server.sacn = _udp_socket(args.sacn_host)

    print("Light Studio bridge listening on http://127.0.0.1:%d" % args.port)
    print("  Art-Net  -> %s:%d" % (args.artnet_host, ARTNET_PORT))
    print("  sACN     -> %s:%d" % (args.sacn_host, SACN_PORT))
    print("Leave this window open while you run the show. Ctrl-C to stop.")

    def tick():
        while True:
            threading.Event().wait(5)
            sys.stdout.write("\r  frames forwarded: %d%s   " % (
                _state["frames"], ("  last error: " + _state["last"]) if _state["last"] else ""))
            sys.stdout.flush()

    threading.Thread(target=tick, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
