import os
import psycopg2

DATABASE_HOST = os.environ.get('DATABASE_HOST', '')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'iotmodbus')
DATABASE_USER = os.environ.get('DATABASE_USER', '')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', '')

con = None
curs_obj = None

def init_connection():
    if con is None or curs_obj is None:
        con = psycopg2.connect(
            database=DATABASE_NAME,
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            host=DATABASE_HOST,
            port= '5432'
        )
        curs_obj = con.cursor()


def log_to_db(device, key_name, register_address, value):
    # create table modbusdata (deviceId varchar(255), time timestamp, key varchar(255), register varchar(255), value float);
    try:
        init_connection()
        curs_obj.execute("""
            INSERT INTO modbusdata(time, key, register, value)
            VALUES('2024-10-10T00:00:00Z', "voltage", 3434, 345.66);
        """)
    except Exception as ex:
        print("log_to_db error")
        print(ex)
        con = None
        curs_obj = None


if __name__ == "__main__":
    log_to_db("dev-1", "test_key", "3330", 234.5)
    print("Data Inserted")
