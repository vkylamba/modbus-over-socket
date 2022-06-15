import binascii
from socket_client_handler import ClientHandler


class FakeConnection:

    data = [
        b'Heartbeat ooo',
        b'\x02\x06\x01\r\x00\x00\x02\xcdRPI M20A,\xfd\xde\x03',

        b'\x02\x06\x01\x9d`\x01203FA0E0000244',
        b'08181102961321209010',
        b'0\x02\x1a\x11%\x01=\x10,\x02,\x11%\x11\n\x02\xcc\x06\xdc\x13',
        b"\x8a\x10\xac\x13\x89\x11'\x02\xba\x06\xe0\x13\x8a\x11\x1e\x13\x89\x10\xc5\x02",
        b'\xbe\x07\x1a\x13\x8a\x10\xed\x13\x89\x15\x0b\x02\x06\n\xdc\x11\xb9\x02B\n',
        b'4\x14\xd6\rw\r\x97\x00\x00\x17\xd4\x00\x00\x19\xe7\x00\x004\x9e\x00',
        b'm\xddU\x00,\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
        b'\x00\\\x9e\x03'
        # b"\x02\x06\x01\x9d`\x01203FA0E0000244081811029613212090100\x02\x1a\x11%\x01=\x10,\x02,\x11%\x11\n\x02\xcc\x06\xdc\x13\x8a\x10\xac\x13\x89\x11'\x02\xba\x06\xe0\x13\x8a\x11\x1e\x13\x89\x10\xc5\x02\xbe\x07\x1a\x13\x8a\x10\xed\x13\x89\x15\x0b\x02\x06\n\xdc\x11\xb9\x02B\n4\x14\xd6\rw\r\x97\x00\x00\x17\xd4\x00\x00\x19\xe7\x00\x004\x9e\x00m\xddU\x00,\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\\\x9e\x03"
    ]
    index = 0

    def recv(self, size):
        if self.index < len(self.data):
            idx = self.index
            self.index = self.index + 1
            resp = self.data[idx]
            data_hex = binascii.hexlify(resp)
            print(f"RECEIVED FROM SOCKET(HEX): {data_hex}")
            print(f"RECEIVED FROM SOCKET: {resp}")
            return resp
        else:
            return b''

    def sendall(self, data):
        data_hex = binascii.hexlify(data)
        print(f"SENT TO SOCKET(HEX): {data_hex}")
        print(f"SENT TO SOCKET: {data}")
        # data_back = "".join([chr(int(x, 16)) for x in data_hex.split()])
        # resp = "02 01 02 0a 11 3b 50"
        # resp = "".join([chr(int(x, 16)) for x in resp.split()])
        # self.data.append(resp)


if __name__ == "__main__":

    connection = FakeConnection()

    client_handler = ClientHandler(
        connection,
        1024
    )
    while True:
        client_handler.serve()
