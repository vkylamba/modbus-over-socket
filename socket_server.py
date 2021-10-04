import socket
import sys

from loggers.console_logger import logger
from socket_client_handler import ClientHandler

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind the socket to the address given on the command line
server_name = sys.argv[1]
server_address = (server_name, 8024)
logger.info(sys.stderr, 'starting up on %s port %s' % server_address)
sock.bind(server_address)
sock.listen(5)

while True:
    logger.info(sys.stderr, 'waiting for a connection')
    connection, client_address = sock.accept()
    try:
        logger.info(sys.stderr, 'client connected:', client_address)
        client_handler = ClientHandler(
            connection,
            client_address
        )
        while True:
            client_handler.serve()
    finally:
        connection.close()
