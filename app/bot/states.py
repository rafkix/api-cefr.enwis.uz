from aiogram.fsm.state import State, StatesGroup

class UserRegisterState(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_username = State()
    waiting_for_email = State()
    waiting_for_password = State()
    waiting_for_age = State()
    waiting_for_level = State()
    waiting_for_phone = State() # Telefon oxiriga ko'chirildi