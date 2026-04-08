from aiogram.fsm.state import State, StatesGroup


class AuthFlow(StatesGroup):
    waiting_contact_login = State()
    waiting_contact_verify = State()


class AdminStates(StatesGroup):
    idle = State()