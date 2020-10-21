import peewee as pw
import config
import states

user_db = pw.SqliteDatabase(config.user_db_path)

class User(pw.Model):
    vk_id = pw.CharField(primary_key=True)
    group = pw.CharField(null=True)
    first_name = pw.CharField()
    last_name = pw.CharField()
    state = pw.CharField(default=states.USER_NEW)
    state_context = pw.CharField(null=True)

    class Meta:
        database = user_db
