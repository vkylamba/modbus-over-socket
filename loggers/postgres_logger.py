import os
import psycopg2
from datetime import datetime

DATABASE_HOST = os.environ.get('DATABASE_HOST', '')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'iotmodbus')
DATABASE_USER = os.environ.get('DATABASE_USER', '')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', '')

con, curs_obj = None, None

def init_connection():
    global con
    con = psycopg2.connect(
        database=DATABASE_NAME,
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
        host=DATABASE_HOST,
        port= '5432'
    )
    con.autocommit = True
    curs_obj = con.cursor()
    return curs_obj


def log_to_db(device, key_name, register_address, value):
    # create table modbusdata (deviceId varchar(255), time timestamp, key varchar(255), register varchar(255), value varchar(255));
    global curs_obj
    time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if curs_obj is None:
            curs_obj = init_connection()
        curs_obj.execute(f"""
            INSERT INTO modbusdata(deviceId, time, key, register, value)
            VALUES('{device}', '{str(time)}', '{str(key_name)}', '{str(register_address)}', '{str(value)}');
        """)
        con.commit()
    except Exception as ex:
        print("log_to_db error")
        print(ex)
        curs_obj = None


if __name__ == "__main__":
    log_to_db("dev-1", "test_key", "3330", 234.5)
    print("Data Inserted")
