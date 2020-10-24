from vk_api.keyboard import VkKeyboard, VkKeyboardColor

empty = VkKeyboard()
empty.keyboard['buttons'] = []

init = VkKeyboard(one_time=False)
init.add_button('11', VkKeyboardColor.POSITIVE)
init.add_button('10', VkKeyboardColor.POSITIVE)
init.add_line()
init.add_button('Задать вопрос куратору', VkKeyboardColor.PRIMARY)
init.add_line()
init.add_button('Отмена', VkKeyboardColor.NEGATIVE)

groups = VkKeyboard(one_time=True)
groups.add_button('11', VkKeyboardColor.POSITIVE)
groups.add_line()
groups.add_button('10', VkKeyboardColor.POSITIVE)
groups.add_line()
groups.add_button('Отмена', VkKeyboardColor.NEGATIVE)

admin_default = VkKeyboard(one_time=False)
admin_default.add_button('Написать классу', VkKeyboardColor.POSITIVE)
admin_default.add_line()
admin_default.add_button('Написать отдельным людям', VkKeyboardColor.POSITIVE)
admin_default.add_line()
admin_default.add_button('Посмотреть список прочитавших')

cancel = VkKeyboard(one_time=False)
cancel.add_button('Отмена', VkKeyboardColor.NEGATIVE)
