import peewee as pw
import config
import states

user_db = pw.MySQLDatabase(config.user_db_path)

class User(pw.Model):
    vk_id = pw.CharField(primary_key=True, max_length=128)
    group = pw.CharField(null=True, index=True)
    first_name = pw.CharField()
    last_name = pw.CharField(index=True)
    state = pw.CharField(default=states.USER_NEW)
    state_context = pw.CharField(null=True)

    class Meta:
        database = user_db


User.create_table()
