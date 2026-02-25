from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_broadcast_text = State()
    waiting_user_search = State()

class AuthFlow(StatesGroup):
    waiting_contact_login = State()
    waiting_contact_verify = State()
    waiting_contact_forgot = State()
    waiting_contact_password = State()
    waiting_new_password = State()