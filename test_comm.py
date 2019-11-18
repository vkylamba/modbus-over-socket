from client_handler import ClientHandler


class FakeConnection:

    data = [
        b'Heartbeat ooo',
    ]
    index = 0

    def recv(self, size):
        if self.index < len(self.data):
            idx = self.index
            self.index = self.index + 1
            return self.data[idx]
        else:
            return ''

    def sendall(self, data):
        data_hex = " ".join("{:02x}".format(ord(c)) for c in data)
        print(f"SENT TO SOCKET: {data_hex}")
        # data_back = "".join([chr(int(x, 16)) for x in data_hex.split()])
        resp = "02 01 02 0a 11 3b 50"
        resp = "".join([chr(int(x, 16)) for x in resp.split()])
        self.data.append(resp)


if __name__ == "__main__":

    connection = FakeConnection()

    client_handler = ClientHandler(
        connection,
        1024,
        "device_conf.json"
    )
    while True:
        client_handler.serve()
