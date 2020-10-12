

class DeltaDataParser:

    def parse(self, command_resp, data_type, key_name):
        if data_type == "json" and isinstance(command_resp, list):
            return command_resp[0].get(key_name)
        if data_type == "json" and isinstance(command_resp, dict):
            return command_resp.get(key_name)
        return command_resp
