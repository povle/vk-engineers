import time
import logging
import peewee as pw
import states
from config import config

user_db = pw.MySQLDatabase(**config['db']['config'])

class User(pw.Model):
    vk_id = pw.CharField(primary_key=True, max_length=128)
    group = pw.CharField(null=True, index=True)
    first_name = pw.CharField()
    last_name = pw.CharField(index=True)
    state = pw.CharField(default=states.USER_NEW)
    state_context = pw.CharField(null=True)

    class Meta:
        database = user_db


exc = None
for _ in range(config['db']['connection_retries']):
    try:
        User.create_table()
        logging.info('Connected to db')
    except pw.OperationalError as e:
        logging.error(f'Database connection error: {e}')
        exc = e
        time.sleep(config['db']['retry_interval'])
    else:
        break
else:
    raise exc
