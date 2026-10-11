# ?????? ??????? Hattori: bot/handlers/modules/mems/fsm.py
from aiogram.fsm.state import StatesGroup, State


class AutoAdd(StatesGroup):
	toggle = State()