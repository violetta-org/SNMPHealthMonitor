import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

def create_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=DictCursor,
        autocommit=True
    )

@contextmanager
def get_db():
    conn = create_connection()
    try:
        yield conn
    finally:
        conn.close()

