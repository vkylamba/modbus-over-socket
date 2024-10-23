import socket
import sys

from loggers.console_logger import logger
from socket_client_handler import ClientHandler


def main():
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind the socket to the address given on the command line
    server_name = sys.argv[1]
    server_address = (server_name, 8024)
    logger.info('starting up on %s port %s' % server_address)
    sock.bind(server_address)
    sock.listen(5)

    connection = None
    while True:
        try:
            logger.info('waiting for a connection')
            connection, client_address = sock.accept()
            logger.info(f'client connected: {client_address}')
            client_handler = ClientHandler(
                connection,
                client_address
            )
            while True:
                client_handler.serve()
        except Exception as ex:
            logger.exception(ex)
        finally:
            connection.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logger.exception("Failed to start server: ")
        logger.exception(ex)
