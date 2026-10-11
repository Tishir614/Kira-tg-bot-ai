import re
from aiogram.filters import BaseFilter
from aiogram.types import Message

TRIGGER = "кира что за аниме"

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class KiraAnimeFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.text:
            text = normalize(message.text)
            if text == TRIGGER and message.reply_to_message and message.reply_to_message.photo:
                return True

        if message.photo and message.caption:
            caption = normalize(message.caption)
            if TRIGGER in caption:
                return True

        return False