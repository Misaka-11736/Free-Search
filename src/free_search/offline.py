"""Block external networking while allowing Windows asyncio's internal wake-up pipe."""
import ipaddress
import socket
import sys
import threading


def install_network_guard():
    context = threading.local()
    original_pair = socket.socketpair

    def socketpair(*args, **kwargs):
        # Windows implements socketpair with one private TCP loopback connection.
        context.creating_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            context.creating_pair = False

    def audit(event, args):
        if event == "socket.connect" and getattr(context, "creating_pair", False):
            address = args[1]
            if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
                return
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise PermissionError("完全离线版禁止网络访问")

    socket.socketpair = socketpair
    sys.addaudithook(audit)
