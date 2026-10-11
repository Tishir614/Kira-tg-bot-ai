from aiogram.fsm.state import State, StatesGroup


class CharacterCreation(StatesGroup):
    choosing_name = State()
    choosing_race = State()
    choosing_class = State()
    writing_description = State()


class SupportTicket(StatesGroup):
    waiting_question = State()
