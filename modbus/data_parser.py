import struct
from decimal import Decimal
from loggers.console_logger import logger

class Convert:

    def float_to_decimal(self, f):  # float to decimal conversion
        return Decimal(f)  # just pass the float to decimal constructor

    def signed_to_unsigned(self, data, size):
        result = 0
        for x in data[0:size]:
            result = (result << 8) | x
        return result

    def bit32_list_to_decimal(self, integer):
        xx = float(struct.unpack('!f', struct.pack(
            '!I', (integer[0] << 16) | integer[1]))[0])
        return xx

    def bit64_list_to_decimal(self, integer):
        xx = float(struct.unpack('!f', struct.pack(
            '!I', (integer[0] << 32) | integer[1]))[0])
        return xx

    def bit16_list_to_decimal(self, integer):
        xx = float(struct.unpack('!f', struct.pack(
            '!I', (integer[0] << 8) | integer[1]))[0])
        return xx

    def bit8_list_to_decimal(self, integer):
        xx = float(struct.unpack('!f', struct.pack(
            '!I', integer[0] | integer[1]))[0])
        return xx

    def hex_string_to_float(self, binary_data):
        FLOAT = 'f'
        fmt = '<' + FLOAT * (len(binary_data) // struct.calcsize(FLOAT))
        numbers = struct.unpack(fmt, binary_data)
        # print(numbers)
        return numbers

    def float_to_integer(self, value):  # float to integer conversion
        return int(round(value))

    def int_to_binary(self, value, bits):  # integer to binary
        return bin(value).replace('0b', '').rjust(bits, '0')

    def float_to_bin(self, num):  # float to binary
        return bin(struct.unpack('!I', struct.pack('!f', num))[0])[2:].zfill(32)

    def bin_to_float(self, binary):  # binary to float
        return struct.unpack('!f', struct.pack('!I', int(binary, 2)))[0]

    def interpret_as_string(self, x):
        xx = str(float(x / 3))
        return xx

    def byte_to_float(self, bytes):
        return struct.unpack('f', bytes)
    
    def to_float(self, bytes_list):
        float_value = struct.unpack('>f', bytes(bytes_list))[0]
        return float_value


class DataParser:

    def __init__(self):
        self.translator = Convert()

    def check_if_decimal(self, data):
        xx = type(data)
        return xx

    def parse(self, data, data_type):
        logger.info(f"Data parser input - data {data}, data_type: {data_type}")
        # numbytes = ord(data[0])
        data = [ord(data[i]) for i in range(1, len(data))]

        if data_type == 'UINT32':
            return self.translator.signed_to_unsigned(data, 4)
        elif data_type == 'UINT48(num,num,divider)':
            num1 = self.translator.signed_to_unsigned(data, 2)
            num2 = self.translator.signed_to_unsigned(data[2:4], 2)
            divider = self.translator.signed_to_unsigned(data[4:6], 2)
            if divider > 1:
                return (num1 * divider + num2) / (divider / 10)
            return (num1 * divider + num2) / divider
        elif data_type == 'UINT64':
            return self.translator.signed_to_unsigned(data, 8)
        elif data_type == 'UINT16':
            return self.translator.signed_to_unsigned(data, 2)
        elif data_type == 'UINT8':
            return self.translator.signed_to_unsigned(data, 1)
        elif data_type == 'INT32':
           return self.translator.signed_to_unsigned(data, 4)
        elif data_type == 'INT64':
            return self.translator.signed_to_unsigned(data, 8)
        elif data_type == 'INT16':
            return self.translator.signed_to_unsigned(data, 2)
        elif data_type == 'INT8':
            return self.translator.signed_to_unsigned(data, 1)
        elif data_type == 'FLOAT':
            return self.translator.to_float(data)
        else:
            xx = "Unknown data type"
            return xx
