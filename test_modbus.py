import serial
import minimalmodbus

# port name, slave address (in decimal)
instrument = minimalmodbus.Instrument(
    '/dev/tty.usbserial-14110',
    3
)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity   = serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout  = 1.5          # seconds


print(instrument.address)                         # this is the slave address number
instrument.mode = minimalmodbus.MODE_RTU   # rtu or ascii mode
instrument.clear_buffers_before_each_transaction = True

## Read temperature (PV = ProcessValue) ##
temperature = instrument.read_register(40002, 1, functioncode=4)  # Registernumber, number of decimals
print(temperature)
