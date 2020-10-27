import vk_api
import time
import logging
import keyboards
import states
import config
from user import User, user_db
from vk_api.bot_longpoll import VkBotMessageEvent


logger = logging.getLogger('vk-engineers.'+__name__)

class Bot:
    def __init__(self, token):
        self.token = token
        self.vk_session = vk_api.VkApi(token=self.token)
        self.vk = self.vk_session.get_api()
        self.handlers = {
            states.USER_NEW: self.handle_user_new,
            states.USER_INIT: self.handle_user_init,
            states.USER_DEFAULT: self.handle_user_default,
            states.ADMIN_DEFAULT: self.handle_admin_default,
            states.ADMIN_BROADCAST_GROUP_SELECTION: self.handle_broadcast_group_selection,
            states.ADMIN_RECEIVER_GROUP_SELECTION: self.handle_receiver_group_selection,
            states.ADMIN_UNREAD_GROUP_SELECTION: self.handle_unread_group_selection,
            states.ADMIN_RECEIVER_SELECTION: self.handle_receiver_selection,
            states.ADMIN_MESSAGE_INPUT: self.handle_message_input,
        }

    def handle(self, data):
        event = data
        if type(event) is not VkBotMessageEvent:
            event = VkBotMessageEvent(event)
        msg = event.object
        if msg.text:
            with user_db:
                user = User.get_or_none(User.vk_id == str(msg.peer_id))
                if user is None:
                    logger.info(f'New user {msg.peer_id}')
                    user_info = self.vk.users.get(user_ids=msg.peer_id)[0]
                    first_name = user_info.get('first_name', '')
                    last_name = user_info.get('last_name', '')
                    user = User.create(
                        vk_id=str(msg.peer_id),
                        first_name=first_name,
                        last_name=last_name,
                        state=states.USER_NEW
                    )
                try:
                    handler = self.handlers.get(user.state, self.handle_other)
                    handler(msg, user)
                    logger.info(f'Handled by {handler.__name__} : {msg}')
                    user.save()
                except Exception as e:
                    logger.exception(e)
                    self.set_user_state(user, user.state)
                    self.send(f'Ошибка: {e}', msg.peer_id)
        logger.debug(f'No text: {msg}')

#------------------------------------STAGES-------------------------------------
    def handle_user_new(self, msg, user):
        if msg.peer_id in config.admins:
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Добро пожаловать')
        else:
            self.set_user_state(user, states.USER_INIT)
        return True

    def handle_user_init(self, msg, user):
        if msg.text == 'Задать вопрос куратору':
            message = '''Любые вопросы вы можете задать [elenasergeevnas|Елене Сергеевне] - куратору Инженерного класса Школы 2036'''
            self.send(message, msg.peer_id)
        elif msg.text in ('10', '11'):
            message = '''Спасибо. Теперь ты подключен к боту "Инженеры 2036" и будешь в курсе важных событий.
Если захочешь отписаться - напиши стоп'''
            self.set_user_state(user, states.USER_DEFAULT, message=message)
            user.group = msg.text
        else:
            self.set_user_state(user, states.USER_NEW, message='Если передумаешь - отправь любое сообщение.')
        return True

    def handle_user_default(self, msg, user):
        text = msg.text.casefold()
        if text == 'стоп':
            user.delete_instance()
            self.send('Если передумаешь - отправь любое сообщение.', msg.peer_id)
            logger.info(f'Deleted {user.vk_id}')

    def handle_admin_default(self, msg, user):
        if msg.peer_id not in config.admins:
            self.set_user_state(user, states.USER_NEW, message='Вы больше не администратор')
        elif msg.text == 'Написать классу':
            self.set_user_state(user, states.ADMIN_BROADCAST_GROUP_SELECTION)
        elif msg.text == 'Написать отдельным людям':
            self.set_user_state(user, states.ADMIN_RECEIVER_GROUP_SELECTION)
        elif msg.text == 'Посмотреть список прочитавших':
            self.set_user_state(user, states.ADMIN_UNREAD_GROUP_SELECTION)

    def handle_broadcast_group_selection(self, msg, user):
        if msg.text in ('10', '11'):
            self.set_user_state(user, states.ADMIN_MESSAGE_INPUT, state_context=msg.text)
        else:
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Отменено')

    def handle_receiver_group_selection(self, msg, user):
        if msg.text in ('10', '11'):
            self.set_user_state(user, states.ADMIN_RECEIVER_SELECTION, state_context=msg.text)
        else:
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Отменено')

    def handle_unread_group_selection(self, msg, user):
        message = 'Отменено'
        if msg.text in ('10', '11'):
            ans = ''
            ids = []
            query = User.select().where(User.group == msg.text).order_by(User.last_name, User.first_name)
            for receiver in query:
                ids.append(receiver.vk_id)
            vk_data = []
            if ids:
                vk_data = self.vk.messages.getConversationsById(peer_ids=','.join(ids))['items']
            vk_data = {str(x['peer']['id']): x for x in vk_data}
            for n, receiver in enumerate(query):
                try:
                    ans += f'{n+1}. {receiver.last_name} {receiver.first_name} '

                    read = vk_data[receiver.vk_id]['out_read'] == vk_data[receiver.vk_id]['last_message_id']
                    if not vk_data[receiver.vk_id]['can_write']['allowed']:
                        emoji = '❗️'
                    else:
                        emoji = '✅' if read else '❌'

                    ans += emoji
                    ans += '\n'
                except Exception as e:
                    ans += f'{n+1}. {receiver.last_name} {receiver.first_name} {e}\n'
            if not ids:
                ans = 'В выбранном классе нет ни одного ученика'
            message = ans
        self.set_user_state(user, states.ADMIN_DEFAULT, message=message)

    def handle_receiver_selection(self, msg, user):
        if msg.text == 'Отмена':
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Отменено')
        else:
            ctx = []
            nums = msg.text.split()
            query = User.select().where(User.group == user.state_context).order_by(User.last_name, User.first_name)
            for n, receiver in enumerate(query):
                if str(n+1) in nums:
                    ctx.append(receiver.vk_id)
            if len(ctx) != len(nums):
                self.send('Некоторых или всех введенных индексов не существует. Введите номера заново', msg.peer_id)
            else:
                self.set_user_state(user, states.ADMIN_MESSAGE_INPUT, state_context=','.join(ctx))

    def handle_message_input(self, msg, user):
        if msg.text != 'Отмена':
            if user.state_context in ('10', '11'):
                receivers = User.select().where(User.group == user.state_context)
            else:
                receivers = user.state_context.split(',')
            for receiver in receivers:
                try:
                    self.send(msg.text, getattr(receiver, 'vk_id', receiver))
                except Exception:
                    pass
            message = 'Отправлено'
        else:
            message = 'Отменено'
        self.set_user_state(user, states.ADMIN_DEFAULT, message=message)

    def handle_other(self, msg, user):
        pass

#-------------------------------------UTILS-------------------------------------

    def set_user_state(self, user: User, state: str, state_context=None, message=None):
        # i know that this probably should be in User class
        # but most transitions are vk api bound so it's much cleaner here
        keyboard = None
        _message = None

        if state == states.USER_NEW:
            keyboard = keyboards.empty
        elif state == states.USER_INIT:
            _message = 'Выбери свой класс'
            keyboard = keyboards.init
        elif state == states.USER_DEFAULT:
            keyboard = keyboards.empty
        elif state == states.ADMIN_DEFAULT:
            _message = 'ОК'
            keyboard = keyboards.admin_default
        elif state in (
                states.ADMIN_BROADCAST_GROUP_SELECTION,
                states.ADMIN_RECEIVER_GROUP_SELECTION,
                states.ADMIN_UNREAD_GROUP_SELECTION):
            _message = 'Выберите класс'
            keyboard = keyboards.groups
        elif state == states.ADMIN_RECEIVER_SELECTION:
            _message = ''
            query = User.select().where(User.group == state_context).order_by(User.last_name, User.first_name)
            for n, receiver in enumerate(query):
                _message += f'{n+1}. {receiver.last_name} {receiver.first_name}\n'
            if not _message:
                self.set_user_state(user, states.ADMIN_DEFAULT, message='В выбранном классе нет ни одного ученика')
                return
            _message += '\nВведите номера получателей из списка через пробел'
            keyboard = keyboards.cancel
        elif state == states.ADMIN_MESSAGE_INPUT:
            _message = 'Введите сообщение'
            keyboard = keyboards.cancel
        else:
            raise states.StateError
        user.state = state
        user.state_context = state_context
        logger.info(f'Changed {user.vk_id} state to {state}')

        message = message or _message
        if message or keyboard:
            self.send(message, user.vk_id, keyboard=keyboard)

    def send(self, text, to, attachments=[], photos=[], documents=[], keyboard=None):
        _attachments = []
        attachments = attachments.copy()
        if photos or documents:
            upload = vk_api.VkUpload(self.vk)
            if photos:
                for photo in upload.photo_messages(photos=photos):
                    _attachments.append(
                        f"photo{photo['owner_id']}_{photo['id']}")
            for doc in documents:
                attachments.append(upload.document_message(doc, peer_id=to))

        for doc in attachments:
            d = doc[doc['type']]
            s = f"{doc['type']}{d['owner_id']}_{d['id']}"
            if 'access_key' in d:
                s += '_' + d['access_key']
            _attachments.append(s)

        if not text and not _attachments:
            text = 'empty'
        text = str(text)

        if keyboard is not None:
            keyboard = keyboard.get_keyboard()

        rd_id = vk_api.utils.get_random_id()
        self.vk.messages.send(peer_id=int(to), random_id=rd_id, message=text[:4000],
                              attachment=','.join(_attachments), keyboard=keyboard)
        if len(text) > 4000:
            time.sleep(0.4)
            self.send(text[4000:], to)
