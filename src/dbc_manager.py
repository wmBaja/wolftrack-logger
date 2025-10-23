import cantools
import can 
from pprint import pprint 

class DBCManager:
    """Loads, encodes, and decodes CAN messages based on given DBC file."""

    def __init__(self, dbc_path: str):
        self.dbc_path = dbc_path
        self.db = cantools.database.load_file(dbc_path)

    def decode(self, message: can.Message) -> dict:
        return self.db.decode_message(message.arbitration_id, message.data)

    #encode() was created to help test decode function.
    def encode(self, message_name: str, list: dict) -> can.Message:
        message = self.db.get_message_by_name(message_name)
        signals = message.encode(list)
        return can.Message(arbitration_id=message.frame_id, is_extended_id=message.is_extended_frame, data=signals)

    def get_info(self, message_name: str) -> dict:
        info = self.db.get_message_by_name(message_name).signals
        return info

if __name__ == '__main__':
    '''db1 = DBCManager("dbc/motohawk.dbc")
    print(db1.db.messages)
    example_message = db1.db.get_message_by_name('ExampleMessage')

    mess = db1.encode("ExampleMessage", {'Temperature': 250.1, 'AverageRadius': 3.2, 'Enable': 1})
    print(mess)

    print(db1.decode(mess))

    pprint(db1.get_info("ExampleMessage"))'''

