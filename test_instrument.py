
from modbus.data_parser import DataParser as RTUDataParser
from modbus.socket_minimal_modebus import Instrument as RTUInstrument

instrument = RTUInstrument("fake_serial", 1)


# hex_string = '010307d000018487'
# bytes.fromhex(hex_string)

read_energy_command = '0103138C00014165'
response = '0103060a7000430064902b'

command_data, x = instrument.read_registers(5004, 1)

print(f"command_data: {command_data}")


# \x01\x03\x13\x8c\x00\x01Ae
# \x01\x03\x13\xc2\x8c\x00\x01Ae
