import time
import peewee as pw
import config
import states

user_db = pw.MySQLDatabase(**config.db_config)

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
for _ in range(config.db_connection_retries):
    try:
        User.create_table()
    except pw.OperationalError as e:
        exc = e
        time.sleep(config.db_retry_interval)
    else:
        break
else:
    raise exc
