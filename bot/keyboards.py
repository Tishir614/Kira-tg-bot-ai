from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.sql import RaceManager, ClassManager


async def gen_race_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    race_manager = RaceManager()
    races = await race_manager.get_all()
    for race in races:
        builder.button(text=race.name, callback_data=f"setrace+{race.id}+{user_id}")
    builder.adjust(3, repeat=True)
    return builder.as_markup()

async def gen_class_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    class_manager = ClassManager()
    classes = await class_manager.get_all()
    for cl in classes:
        builder.button(text=cl.name, callback_data=f"setclass+{cl.id}+{user_id}")
    builder.adjust(3, repeat=True)
    return builder.as_markup()