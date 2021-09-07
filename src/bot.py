import vk_api
import time
import logging
import json
import keyboards
import states
from config import config
from user import User, user_db
from vk_api.bot_longpoll import VkBotMessageEvent


logger = logging.getLogger('vk-engineers.'+__name__)

class Bot:
    groups = ('10.1', '10.2', '11')

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
        if msg.peer_id in config['vk']['admins']:
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Добро пожаловать')
        else:
            self.set_user_state(user, states.USER_INIT)

    def handle_user_init(self, msg, user):
        if msg.text == 'Задать вопрос куратору':
            message = '''Любые вопросы вы можете задать [elenasergeevnas|Елене Сергеевне] - куратору Инженерного класса Школы 2036'''
            self.send(message, msg.peer_id)
        elif msg.text in self.groups:
            message = '''Спасибо. Теперь ты подключен к боту "Инженеры 2036" и будешь в курсе важных событий.
Если захочешь отписаться - напиши стоп'''
            self.set_user_state(user, states.USER_DEFAULT, message=message)
            user.group = msg.text
        else:
            self.set_user_state(user, states.USER_NEW, message='Если передумаешь - отправь любое сообщение.')

    def handle_user_default(self, msg, user):
        text = msg.text.casefold()
        if text == 'стоп':
            user.delete_instance()
            self.send('Если передумаешь - отправь любое сообщение.', msg.peer_id)
            logger.info(f'Deleted {user.vk_id}')
        else:
            forward = {
                'peer_id': msg.peer_id,
                'conversation_message_ids': [msg.conversation_message_id],
            }
            self.send(' ', ','.join(str(x) for x in config['vk']['admins']), forward=forward)

    def handle_admin_default(self, msg, user):
        if msg.peer_id not in config['vk']['admins']:
            self.set_user_state(user, states.USER_NEW, message='Вы больше не администратор')
        elif msg.text == 'Написать классу':
            self.set_user_state(user, states.ADMIN_BROADCAST_GROUP_SELECTION)
        elif msg.text == 'Написать отдельным людям':
            self.set_user_state(user, states.ADMIN_RECEIVER_GROUP_SELECTION)
        elif msg.text == 'Посмотреть список прочитавших':
            self.set_user_state(user, states.ADMIN_UNREAD_GROUP_SELECTION)
        else:
            reply = self.get_first_forwarded(msg)
            if not reply:
                return
            while self.get_first_forwarded(reply):
                reply = self.get_first_forwarded(reply)
            if reply['from_id'] == reply['peer_id']:
                offset = 1
            else:
                offset = 0

            reply = self.vk.messages.getHistory(
                peer_id=reply['peer_id'],
                start_message_id=reply['id'],
                count=1,
                offset=-offset
            )['items'][0]

            if reply.get('payload'):
                payload = json.loads(reply['payload'])
                if payload.get('min_id') and payload.get('ids'):
                    ids = payload['ids']
                    min_id = payload.get('min_id')
                    if ids in self.groups:
                        ans = self.get_group_unread_list(ids, min_id)
                    else:
                        query = User.select().where(User.vk_id.in_(ids.split(','))).order_by(User.last_name, User.first_name)
                        ans = self.get_unread_list(query, min_id)
                    self.send(ans, msg.peer_id, payload=payload)

    def handle_broadcast_group_selection(self, msg, user):
        if msg.text in self.groups:
            self.set_user_state(user, states.ADMIN_MESSAGE_INPUT, state_context=msg.text)
        else:
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Отменено')

    def handle_receiver_group_selection(self, msg, user):
        if msg.text in self.groups:
            self.set_user_state(user, states.ADMIN_RECEIVER_SELECTION, state_context=msg.text)
        else:
            self.set_user_state(user, states.ADMIN_DEFAULT, message='Отменено')

    def handle_unread_group_selection(self, msg, user):
        message = 'Отменено'
        if msg.text in self.groups:
            message = self.get_group_unread_list(msg.text)
        self.set_user_state(user, states.ADMIN_DEFAULT, message=message)

    def handle_receiver_selection(self, msg, user):
        if msg.text.casefold() == 'отмена':
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
        payload = None
        if not msg.text:
            self.send('Поддерживается только отправка текста. Введите сообщение или напишите "отмена"', msg.peer_id)
            return
        if msg.text.casefold() != 'отмена':
            if user.state_context in self.groups:
                query = User.select().where(User.group == user.state_context)
                receivers = ','.join(receiver.vk_id for receiver in query)
            else:
                receivers = user.state_context

            try:
                vk_data = self.send(msg.text, receivers, source=msg)
                if type(vk_data) is int:
                    min_id = vk_data
                else:
                    min_id = min(x.get('message_id', float('inf')) for x in vk_data)
            except vk_api.exceptions.ApiError:
                min_id = float('inf')

            if min_id < float('inf'):
                message = 'Отправлено'
                payload = {
                    'min_id': min_id,
                    'ids': receivers
                }
            else:
                message = 'Не удалось отправить ни одному из получателей'
        else:
            message = 'Отменено'
        self.set_user_state(user, states.ADMIN_DEFAULT, message=message, payload=payload)

    def handle_other(self, msg, user):
        pass

#-------------------------------------UTILS-------------------------------------
    @staticmethod
    def get_first_forwarded(msg):
        return msg.get('reply_message') or (msg.get('fwd_messages', [])+[None])[0]

    def get_group_unread_list(self, group, msg_id=None):
        query = User.select().where(User.group == group).order_by(User.last_name, User.first_name)
        ids = []
        for receiver in query:
            ids.append(receiver.vk_id)
        if ids:
            ans = self.get_unread_list(query, msg_id)
        else:
            ans = 'В выбранном классе нет ни одного ученика'
        return ans

    def get_unread_list(self, receivers, msg_id=None):
        ans = ''
        vk_data = self.vk.messages.getConversationsById(peer_ids=','.join(x.vk_id for x in receivers))['items']
        vk_data = {str(x['peer']['id']): x for x in vk_data}
        for n, receiver in enumerate(receivers):
            try:
                ans += f'{n+1}. {receiver.last_name} {receiver.first_name} '
                conv = vk_data[receiver.vk_id]
                if msg_id:
                    read = conv['out_read'] >= msg_id
                else:
                    read = conv['out_read'] == conv['last_message_id']
                if not conv['can_write']['allowed']:
                    emoji = '❗️'
                else:
                    emoji = '✅' if read else '❌'

                ans += emoji
                ans += '\n'
            except Exception as e:
                ans += f'{n+1}. {receiver.last_name} {receiver.first_name} {e}\n'
        return ans

    def set_user_state(self, user: User, state: str, state_context=None, message=None, payload=None):
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
            _message += '\nВведите номера получателей из списка через пробел или напишите "отмена"'
            keyboard = keyboards.empty
        elif state == states.ADMIN_MESSAGE_INPUT:
            _message = 'Введите сообщение или напишите "отмена"'
            keyboard = keyboards.empty
        else:
            raise states.StateError
        user.state = state
        user.state_context = state_context
        logger.info(f'Changed {user.vk_id} state to {state}')

        message = message or _message
        if message or keyboard:
            self.send(message, user.vk_id, keyboard=keyboard, payload=payload)

    def send(self, text, to, attachments=[], photos=[], documents=[], keyboard=None, source=None, **kwargs):
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

        if source is not None:
            source = {
                'type': 'message',
                'owner_id': config['vk']['group_id'],
                'peer_id': source.peer_id,
                'conversation_message_id': source.conversation_message_id
            }
            source = json.dumps(source)

        for arg in kwargs:
            if type(kwargs[arg]) is dict:
                kwargs[arg] = json.dumps(kwargs[arg])

        kwargs.update({
            'random_id': vk_api.utils.get_random_id(),
            'message': text[:4000],
            'attachment': ','.join(_attachments),
            'keyboard': keyboard,
            'content_source': source
        })

        if type(to) in (list, tuple):
            to = ','.join(str(x) for x in to)

        if type(to) is str and ',' in to:
            kwargs['peer_ids'] = to
        else:
            kwargs['peer_id'] = to

        response = self.vk.messages.send(**kwargs)
        if len(text) > 4000:
            time.sleep(0.4)
            self.send(text[4000:], to)
        return response
