
from modbus.data_parser import DataParser as RTUDataParser
from modbus.socket_minimal_modebus import Instrument as RTUInstrument
from modbus.socket_minimal_modebus import _hexlify as hexify

instrument = RTUInstrument("fake_serial", 1)


# hex_string = '010307d000018487'
# bytes.fromhex(hex_string)

read_energy_command = '0103138C00014165'
# response_bytes = b'\x01\x03\x06\n~\x00[\x00dy\xed'
response_bytes = b'\x01\x03\x06\n\x80\x00\x17\x00d\x91\xee'
#  HEX format: 01 03 06 0A 7E 00 5B 00 64 79 ED
command_data, x = instrument.read_registers(
    5004,
    1,
    functioncode=3
)

print(f"command_data: {command_data}")

parsed_response = instrument.get_command_response(
    response_bytes,
    3
)

print(f"response: {parsed_response}")

parser = RTUDataParser()

value = parser.parse(parsed_response, "INT16")

print(f"value: {value}")
