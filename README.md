
# Modbus Over Socket

**Modbus Over Socket** is an open-source project that enables a socket server to communicate with IoT gateways over socket connections using the Modbus protocol. This server can interface with any Modbus-capable sensor and supports custom register configurations loaded through JSON files. Data from the connected sensors is collected periodically and can be logged in various formats such as JSON files, databases, or APIs.

## Features

- **Socket Server**: Communicates with IoT gateways over socket connections using the Modbus protocol.
- **Customizable Register Configuration**: Supports loading sensor-specific register configurations in JSON files.
- **Periodic Data Collection**: Gathers data from connected Modbus sensors at regular intervals.
- **Flexible Logging Options**: Logs data to JSON files, databases, or APIs for further processing and analytics.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Example Configuration](#example-configuration)
- [Logging Options](#logging-options)
- [Contributing](#contributing)
- [License](#license)

## Installation

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/modbus-over-socket.git
    cd modbus-over-socket
    ```

2. **Install Dependencies**:  
   Install the required dependencies using:
    ```bash
    pip install -r requirements.txt
    ```

3. **Configure Environment Variables** (if applicable):  
   Set up any necessary environment variables required by your project.

## Configuration

Configuration is managed through JSON files, which define the register mappings for each Modbus sensor connected via the IoT gateway. The main configurations include:

- **Server Configuration**: Define the socket server settings such as host, port, and protocol type.
- **Sensor Register Mapping**: JSON configuration files that specify register addresses and data types for each connected sensor.

### Example Configuration

#### Server Configuration (config/server_config.json)

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 502,
        "protocol": "modbus-tcp"
    },
    "sensors": [
        {
            "id": "sensor1",
            "registers": "config/sensor1_registers.json"
        },
        {
            "id": "sensor2",
            "registers": "config/sensor2_registers.json"
        }
    ]
}
```

#### Sensor Register Mapping (config/sensor1_registers.json)

```json
{
    "registers": [
        {
            "name": "temperature",
            "address": 1001,
            "type": "float"
        },
        {
            "name": "humidity",
            "address": 1002,
            "type": "float"
        }
    ],
    "interval": 5000  // Data collection interval in milliseconds
}
```

## Usage

1. **Start the Server**: Run the server to initiate the Modbus socket connection and start collecting data.
    ```bash
    python server.py
    ```

2. **Monitor Logs**: View real-time data collection in the logs or in the specified output locations.

## Logging Options

Data collected by the server can be logged in different formats:

- **JSON Logs**: Save data in JSON format to a local file.
- **Database Logging**: Log data to a configured database (e.g., SQLite, MySQL, PostgreSQL).
- **API Logging**: Send data to a remote API endpoint.

Configure logging options in the `logging` section of the main configuration file, specifying the desired output format and any relevant connection details.

## Contributing

Contributions are welcome! If you'd like to improve this project or report issues, please feel free to open issues and pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/NewFeature`)
3. Commit your changes (`git commit -m 'Add some feature'`)
4. Push to the branch (`git push origin feature/NewFeature`)
5. Open a pull request
