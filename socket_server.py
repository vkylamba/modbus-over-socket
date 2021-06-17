import socket
import sys

from socket_client_handler import ClientHandler

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind the socket to the address given on the command line
server_name = sys.argv[1]
server_address = (server_name, 8024)
print(sys.stderr, 'starting up on %s port %s' % server_address)
sock.bind(server_address)
sock.listen(1)

while True:
    print(sys.stderr, 'waiting for a connection')
    connection, client_address = sock.accept()
    try:
        print(sys.stderr, 'client connected:', client_address)
        client_handler = ClientHandler(
            connection,
            client_address
        )
        while True:
            client_handler.serve()
    finally:
        connection.close()
