from flask import Flask, request
from bot import Bot
import logging
import config

logging.config.fileConfig('logger.conf')
logger = logging.getLogger('vk-engineers.'+__name__)

TOKEN = config.token
confirmation_code = config.confirmation_code
SECRET = config.secret

server = Flask(__name__)
bot = Bot(token=TOKEN)

last_msgs = []


@server.route('/', methods=['POST'])
def handle():
    try:
        data = request.get_json(force=True, silent=True)
        logger.debug(f'POST: {data}')
        if not data or 'type' not in data or data.get('secret') != SECRET:
            logger.warning('Incorrect data')
            return 'not ok'
        if data['type'] == 'confirmation':
            return confirmation_code
        elif data['type'] == 'message_new':
            global last_msgs
            if data not in last_msgs:
                last_msgs = last_msgs[-9:] + [data]
                bot.handle(data)
            return 'ok'
    except Exception as e:
        logger.error(e)
    return 'ok'


if __name__ == "__main__":
    server.run(host="localhost", port=7772)
