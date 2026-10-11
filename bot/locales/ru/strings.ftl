start_message = 🦊 <b>Kira на связи</b>
 Привет, { $user }!
 <blockquote>Умная локальная помощница, собеседница и центр твоего сообщества.</blockquote>

 { $character }

user_no_character = ✨ У тебя пока нет персонажа. Можешь создать его кнопкой ниже.

user_character = <b><i>Имя</i>: { $name }</b>
 <i>Класс</i>: { $character_class }
 <i>Раса</i>: { $race }

 <blockquote>{ $description }</blockquote>

 { $married }

married = 🫥 В браке с <a href="tg://user?id={ NUMBER($user_id, useGrouping: 0) }">{ $married }</a>

set_name_character = 🫥 Окей! Назови своего персонажа. Имя должно содержать от 2 до 20 символов.
set_race_character =🫥 Выбери расу для своего персонажа:
set_class_character =🫥 Выбери класс для своего персонажа:
set_description_character =🫥 Опиши своего персонажа. Описание должно содержать от 10 до 500 символов.
name_too_long = 🫥 Имя слишком длинное! Нужно обязательно до 20 символов. Придумай другое
name_too_short = 🫥 Имя слишком короткое! Нужно обязательно от 2 символов. Придумай другое

name_description_long = 🫥 Описание слишком длинное! Нужно обязательно до 500 символов. Придумай другое

 <blockquote><code>{ $text }</code></blockquote>

name_description_short = 🫥 Описание слишком короткое! Нужно обязательно от 10 символов. Придумай другое

 <blockquote><code>{ $text }</code></blockquote>



private_only = 🫥 Создать персонажа можно только в лс!

group_only_rp_add = 🫥 Добавить рп-команду можно только в группе!
group_only_rp_remove = 🫥 Удалить рп-команду можно только в группе!
supergroup_only = 🫥 Я работаю только в супергруппах. Преобразуйте группу в супергруппу и добавьте меня снова.

text_only = 🫥 Нужно текстовое сообщение. Попробуйте еще раз:
admin_only = 🫥 Только для администрации!
sudo_only = 🫥 Только для суперпользователей!
can_change_info_permission_need = 🫥 Тебе нужно иметь право на <b>изменение профиля группы</b>
sudo_usage = 🫥 Нужен ответ на сообщение, id или @username. Пример: <code>+судо @user</code>
sudo_added = 🫥 Выдала sudo: <a href="tg://user?id={ NUMBER($user_id, useGrouping: 0) }">{ NUMBER($user_id, useGrouping: 0) }</a>
sudo_removed = 🫥 Забрала sudo: <a href="tg://user?id={ NUMBER($user_id, useGrouping: 0) }">{ NUMBER($user_id, useGrouping: 0) }</a>
sudo_already = 🫥 У пользователя уже есть sudo: <a href="tg://user?id={ NUMBER($user_id, useGrouping: 0) }">{ NUMBER($user_id, useGrouping: 0) }</a>
sudo_not_found = 🫥 У пользователя нет sudo: <a href="tg://user?id={ NUMBER($user_id, useGrouping: 0) }">{ NUMBER($user_id, useGrouping: 0) }</a>
sudo_cannot_remove_self = 🫥 Нельзя забирать sudo у самого себя
sudo_cannot_remove_owner = 🫥 Нельзя забирать sudo у владельца: <a href="tg://user?id={ NUMBER($user_id, useGrouping: 0) }">{ NUMBER($user_id, useGrouping: 0) }</a>

race_add_usage = 🫥 Укажи название расы. Пример: <code>+раса Гремлин</code>
race_remove_usage = 🫥 Укажи название расы. Пример: <code>-раса Гремлин</code>
race_added = 🫥 Добавила расу: <b>{ $name }</b>
race_deleted = 🫥 Удалила расу: <b>{ $name }</b>
race_not_found = 🫥 Не нашла расу: <b>{ $name }</b>
race_already_exists = 🫥 Такая раса уже есть: <b>{ $name }</b>

class_add_usage = 🫥 Укажи название класса. Пример: <code>+класс Алхимик</code>
class_remove_usage = 🫥 Укажи название класса. Пример: <code>-класс Алхимик</code>
class_added = 🫥 Добавила класс: <b>{ $name }</b>
class_deleted = 🫥 Удалила класс: <b>{ $name }</b>
class_not_found = 🫥 Не нашла класс: <b>{ $name }</b>
class_already_exists = 🫥 Такой класс уже есть: <b>{ $name }</b>

done_create_character = 🫥 Персонаж создан! 🫥

 { $character }

new_character_btn = Создать персонажа
change_character_btn = Пересоздать персонажа
rp_added = 🫥 Добавила новую рп-команду!

no_username_provided = 🫥 Нужен ответ на сообщение, либо @username!
no_reply = 🫥 Нужен ответ на сообщение!
username_must_start_with_at = 🫥 Юзер должен начинаться на "@"!

rp_deleted = 🫥 Удалила эту рп-команду!
delete_rp_not_found = 🫥 Не нашла такую рп-команду!
no_permission_delete_rp_global =🫥  У тебя нет разрешения на удаление глобальных рп-команд!
no_permission_delete_rp = 🫥 У тебя нет разрешения на удаление рп-команд! Нужно разрешение на изменение профиля группы!
no_rp_here = 🫥 В этом чате нет рп-команд!
rp_too_long_answer = 🫥 Ответ слишком длинный (макс. 100 символов)
rp_too_short_answer = 🫥 Ответ слишком короткий (мин. 5 символов)
rp_too_long_trigger = 🫥 Триггер слишком длинный (макс. 20 символов)
rp_too_short_trigger = 🫥 Триггер слишком короткий (мин. 2 символа)
and = и

rp_changed = 🫥 Изменила существующую рп-команду!
im_here = 🫥 Да-да, я здесь:3 🫥



accept = Принять
deny = Отклонить

marry_request = 🫥 <b><a href="tg://user?id={ NUMBER($user1, useGrouping: 0) }">{ $character1 }</a> предложил встречаться <a href="tg://user?id={ NUMBER($user2, useGrouping: 0) }">{ $character2 }</a>!</b>

 <a href="tg://user?id={ NUMBER($user2, useGrouping: 0) }">{ $character2 }</a> примишь ли ты это предложение? 🫥

unmarry_request =  <b><a href="tg://user?id={ NUMBER($user1, useGrouping: 0) }">{ $character1 }</a> предложил расстаться <a href="tg://user?id={ NUMBER($user2, useGrouping: 0) }">{ $character2 }</a>!</b> 

marry_me = 🫥 А-а-а, Бойчик. Я себя не на помойке нашла. Пошел нахуй:3 🫥

not_for_you = 🫥 Не для тебя!
im_not_have_character = 🫥 Я просто бот! У меня нет и не будет персонажа:/
deny_marry = 🫥 Отклонено
accept_marry = 🫥 Вы теперь вместе!🫥

deny_unmarry = 🫥 Отклонено
accept_unmarry = 🫥 Вы больше не пара!

banned = 🫥 { $user } улетел в бан!
unbanned = 🫥 { $user } вышел из цифрового заточения и снова с вами!

open_private_btn = Перейти в ЛС

help_goto_private = 📚 Открой центр помощи Kira, чтобы увидеть все команды по категориям.

help_message = { $commands }

admin_commands = 🫥 <b>Администрация</b>
 { $commands }

tag_admins = 🫥<b>ОБЩИЙ СБОР</b>🫥
 { $admins }

null_admin_chat = 🛡 Для этой группы ещё не настроен внутренний модераторский чат. Создай отдельный чат для команды и привяжи его командой ниже.

 Добавь меня туда и там же отправь вот эту команду: [ <code>админ-чат { NUMBER($chat_id, useGrouping: 0) }</code> ]

chat_connected = 🫥 Админ-чат подключен!

update_message = 🦊✨ <b>KIRA ОБНОВЛЕНА</b>
 ━━━━━━━━━━━━━━━━━━
 📦 Версия: <code>{ $version }</code>
 🔖 Сборка: <code>{ $hash }</code>

 🌟 <b>Что изменилось</b>
 <blockquote>{ $message }</blockquote>

 ✅ Обновление установлено, Kira снова в сети.
 📚 Полный список возможностей: /help

new_chat_message = 🫥 Спасибо, что добавили меня в свой чат!
 Я постараюсь быть интересной и полезной


exists_chat_message = 🫥 Я снова с вами, ребятки!
 Не могу назвать причину своего ухода, но это уже не важно

rp_header = 🫥 <b>Список РП-команд</b>

no_mems = 🫥 В этом чате пока нет мемов
autoclean_btn = Убрать следы
autoadd_on = 🫥 Автодобавление включено. Просто отправляй стикеры, и я сохраню их как мемы
autoadd_off = 🫥 Автодобавление выключено
mem_count_total = 🫥 Всего мемов: <b>{ NUMBER($total, useGrouping: 0) }</b>
error_reply_need_file = 🫥 Нужен ответ на сообщение с json-файлом backup
error_backup_file_read = 🫥 Не смогла прочитать backup-файл мемов
mem_database_restored = 🫥 Восстановлено мемов: <b>{ NUMBER($mems, useGrouping: 0) }</b>
zero_mems_restored = 🫥 Новых мемов для восстановления не найдено

downloaded_caption = 🍌 <b><a href="{ $link }">{ $author }</a></b>
 <blockquote>{ $title }</blockquote>

anime_wait = 🍌 Анализирую кард... 🍌

anime_limit = 🍌 Сервис распознавания аниме временно недоступен из-за превышения лимита запросов. Поиск аниме заблокирован до завтра.

reply_to_photo_need = 🍌 Мне нужен ответ на фото-фрагмент

anime_not_found = 🍌 Странно... Не нашла такого аниме

anime_info = Похоже на <code><b>{ $name }</b></code> 🍌
 Я уверенна на { $similarity_percent }, что кадр из эпизода { $episode } - { $fragment_time } 🍌

 О <code><b>{ $name }</b></code>:
 <b>Всего эпизодов -</b> { $episodes }
 <b>Статус -</b> { $status }
 <blockquote expandable>{ $description }</blockquote>

web_search_usage = 🔎 Напиши запрос после команды.
Примеры:
• <code>найди Godot 4 mobile</code>
• <code>найди видео lo-fi mix</code>
• <code>найди музыку The Weeknd</code>
• <code>найди картинку фурри лиса</code>
web_search_wait = 🔎 Ищу: <b>{ $query }</b>
web_search_no_results = 🔎 Ничего подходящего не нашла.
web_search_results = 🔎 <b>Результаты поиска по запросу:</b> { $query }

 { $results }

web_download_usage = 📥 Пришли публичную HTTP/HTTPS-ссылку после команды или ответь командой <code>скачай</code> на сообщение со ссылкой.
web_download_wait = 📥 Скачиваю файл из интернета…
web_download_done = 📦 <b>{ $filename }</b>
 Размер: <b>{ $size } МБ</b>
 <a href="{ $link }">Источник</a>
