"""MariaDB connection configuration; never store a password in source."""
import os
from pathlib import Path
import pymysql


def connect():
    options={
        'database':os.environ.get('HYDRO_DB_NAME','hydro_dashboard'),
        'user':os.environ.get('HYDRO_DB_USER','hydro-dashboard'),
        'charset':'utf8mb4','connect_timeout':5,
    }
    secret_file=os.environ.get('HYDRO_DB_PASSWORD_FILE')
    if secret_file:
        options['password']=Path(secret_file).read_text().rstrip('\r\n')
    elif os.environ.get('HYDRO_DB_PASSWORD'):
        options['password']=os.environ['HYDRO_DB_PASSWORD']
    if os.environ.get('HYDRO_DB_HOST'):
        options.update(host=os.environ['HYDRO_DB_HOST'],port=int(os.environ.get('HYDRO_DB_PORT','3306')))
    else:
        options['unix_socket']=os.environ.get('HYDRO_DB_SOCKET','/run/mysqld/mysqld.sock')
    return pymysql.connect(**options)
