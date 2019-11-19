import struct
import binascii

from .crc16 import calcData
from .packet_struct import DELTA_RPI_STRUCT

READ_BYTES = 1024
STX = 0x02
ETX = 0x03
ENQ = 0x05
ACK = 0x06
NAK = 0x15

DEBUG = False


class DeltaInstrument:

    def __init__(self, device, target_address):
        self.device = device
        self.target_address = target_address

    def read_registers(self, register_address, register_count):
        cmd, sub_cmd = register_address.split(',')
        cmd = int(cmd, 16)
        sub_cmd = int(sub_cmd, 16)
        register_count = int(register_count)
        command = self.get_command(
            ENQ,
            cmd,
            sub_cmd,
            addr=self.target_address
        )
        return command, register_count

    def get_command_response(self, data, size):
        resp_array = [
            self.decode_msg(x) for x in self.get_frames_from_raw_data(data)
        ]
        return resp_array

    def get_command(self, req, cmd, subcmd, data=b'', addr=1):
        """
        Send cmd/subcmd (e.g. 0x60/0x01) and optional data to the RS485 bus
        """
        assert req in (ENQ, ACK, NAK)  # req should be one of ENQ, ACK, NAK
        msg = struct.pack('BBBBB', req, addr, 2 + len(data), cmd, subcmd)
        if len(data) > 0:
            msg = struct.pack('5s%ds' % len(data), msg, data)
        crcval = calcData(msg)
        lsb = crcval & (0xff)
        msb = (crcval >> 8) & 0xff
        data = struct.pack('B%dsBBB' % len(msg), STX, msg, lsb, msb, ETX)
        if DEBUG:
            print(">>> SEND:", binascii.hexlify(
                msg), "=>", binascii.hexlify(data))
            print(">>>RAW>>>", data)
        return data

    def decode_msg(self, data):
        req = data['req']
        cmd, cmdsub = struct.unpack('>BB', data['msg'][0:2])
        data['cmd'] = cmd
        data['cmdsub'] = cmdsub
        data['raw'] = data['msg'][2:]
        if req == NAK:
            print("NAK value received: cmd/subcmd request was invalid".format(req))
        elif req == ENQ:
            if DEBUG:
                print("ENQ value received: request from master (datalogger)")
        elif req == ACK:
            if DEBUG:
                print("ACK value received: response from slave (inverter)")
            data['values'] = struct.unpack(DELTA_RPI_STRUCT, data['raw'])
        if DEBUG:
            pprint(data)
        return data

    def get_frames_from_raw_data(self, data):
        idx = 0
        while idx + 9 <= len(data):
            if data[idx] != STX:
                idx += 1
                continue
            stx, req, addr, size = struct.unpack('>BBBB', data[idx:idx + 4])
            if req not in (ENQ, ACK, NAK):
                print(
                    "Bad req value: {:02x} (should be one of ENQ/ACK/NAK)".format(req))
                idx += 1
                continue
            if idx + 4 + size >= len(data):
                print("Can't read %d bytes from buffer" % size)
                idx += 1
                continue
            msg, lsb, msb, etx = struct.unpack(
                '>%dsBBB' % size, data[idx + 4:idx + 7 + size])
            if etx != ETX:
                print("Bad ETX value: {:02x}".format(etx))
                idx += 1
                continue
            crc_calc = calcData(data[idx + 1:idx + 4 + size])
            crc_msg = msb << 8 | lsb
            if crc_calc != crc_msg:
                print("Bad CRC check: %s <> %s" %
                      (binascii.hexlify(crc_calc), binascii.hexlify(crc_msg)))
                idx += 1
                continue

            if DEBUG:
                print(">>> RECV:", binascii.hexlify(
                    data), "=>", binascii.hexlify(msg))
            yield {
                "stx": stx,
                "req": req,
                "addr": addr,
                "size": size,
                "msg": msg,
                "lsb": lsb,
                "msb": msb,
                "etx": etx,
            }
            idx += 4 + size
