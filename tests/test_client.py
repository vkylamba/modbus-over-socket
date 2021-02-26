#!/usr/bin/env python3

import socket

HOST = '168.119.153.236'  # Standard loopback interface address (localhost)
PORT = 8024        # Port to listen on (non-privileged ports are > 1023)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.sendall(b'Heartbeat ooo')
    data = s.recv(1024)

print('Received', repr(data))