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
        self.stages = [
            self.stage_init_user,
            self.stage_handle_user_init,
            self.stage_handle_user_default,
            self.stage_handle_admin_default,
            self.stage_handle_broadcast_group_selection,
            self.stage_handle_receiver_selection,
            self.stage_handle_message_input,
        ]

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
                for stage in self.stages:
                    try:
                        if stage(msg, user):
                            logger.info(f'Handled by {stage.__name__} : {msg}')
                            user.save()
                            return
                    except Exception as e:
                        logger.exception(e)
                        self.set_user_state(user, user.state)
                        self.send(f'Ошибка: {e}', msg.peer_id)
            logger.debug(f'Rejected by all stages : {msg}')
        logger.debug(f'No text: {msg}')

#------------------------------------STAGES-------------------------------------
    def stage_init_user(self, msg, user):
        if user.state == states.USER_NEW:
            if msg.peer_id in config.admins:
                self.set_user_state(user, states.ADMIN_DEFAULT)
            else:
                self.set_user_state(user, states.USER_INIT)
            return True

    def stage_handle_user_init(self, msg, user):
        if user.state == 'user_init':
            if msg.text in ('10', '11'):
                self.set_user_state(user, states.USER_DEFAULT)
                user.group = msg.text
                self.send('Спасибо. Если захочешь отписаться - напиши стоп', msg.peer_id)
            else:
                self.set_user_state(user, states.USER_NEW)
                self.send('Если передумаешь - отправь любое сообщение.', msg.peer_id)
            return True

    def stage_handle_user_default(self, msg, user):
        if user.state == states.USER_DEFAULT:
            text = msg.text.casefold()
            if text == 'стоп':
                user.delete_instance()
                self.send('Если передумаешь - отправь любое сообщение.', msg.peer_id)
            return True

    def stage_handle_admin_default(self, msg, user):
        if user.state == states.ADMIN_DEFAULT:
            if msg.text == 'Написать классу':
                self.set_user_state(user, states.ADMIN_BROADCAST_GROUP_SELECTION)
            elif msg.text == 'Написать отдельным людям':
                self.set_user_state(user, states.ADMIN_RECEIVER_SELECTION)
            return True

    def stage_handle_broadcast_group_selection(self, msg, user):
        if user.state == states.ADMIN_BROADCAST_GROUP_SELECTION:
            if msg.text in ('10', '11'):
                self.set_user_state(user, states.ADMIN_MESSAGE_INPUT, state_context=msg.text)
            else:
                self.set_user_state(user, states.ADMIN_DEFAULT)
            return True

    def stage_handle_receiver_selection(self, msg, user):
        if user.state == states.ADMIN_RECEIVER_SELECTION:
            if msg.text == 'Отмена':
                self.set_user_state(user, states.ADMIN_DEFAULT)
            else:
                ctx = []
                nums = msg.text.split()
                query = User.select().where(User.group.in_(('10', '11'))).order_by(User.last_name, User.first_name)
                for n, receiver in enumerate(query):
                    if str(n+1) in nums:
                        ctx.append(receiver.vk_id)
                self.set_user_state(user, states.ADMIN_MESSAGE_INPUT, state_context=','.join(ctx))
            return True

    def stage_handle_message_input(self, msg, user):
        if user.state == states.ADMIN_MESSAGE_INPUT:
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
            self.set_user_state(user, states.ADMIN_DEFAULT)
            return True

#-------------------------------------UTILS-------------------------------------

    def set_user_state(self, user: User, state: str, state_context=None):
        # i know that this probably should be in User class
        # but most transitions are vk api bound so it's much cleaner here
        if state == states.USER_NEW:
            pass
        elif state == states.USER_INIT:
            self.send('Выбери свой класс', user.vk_id, keyboard=keyboards.groups)
        elif state == states.USER_DEFAULT:
            pass
        elif state == states.ADMIN_DEFAULT:
            self.send('ОК', user.vk_id, keyboard=keyboards.admin_default)
        elif state == states.ADMIN_BROADCAST_GROUP_SELECTION:
            self.send('Выберите класс', user.vk_id, keyboard=keyboards.groups)
        elif state == states.ADMIN_RECEIVER_SELECTION:
            receivers = ''
            query = User.select().where(User.group.in_(('10', '11'))).order_by(User.last_name, User.first_name)
            for n, receiver in enumerate(query):
                receivers += f'{n+1}. {receiver.last_name} {receiver.first_name}\n'
            self.send(receivers, user.vk_id, keyboard=keyboards.cancel)
            self.send('Введите номера получателей из списка через пробел', user.vk_id)
        elif state == states.ADMIN_MESSAGE_INPUT:
            self.send('Введите сообщение', user.vk_id, keyboard=keyboards.cancel)
        else:
            raise states.StateError
        user.state = state
        user.state_context = state_context

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
