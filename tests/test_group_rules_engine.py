from bot.rules_engine import inspect_text


def ids(text: str, **kwargs):
    return {hit.rule_id for hit in inspect_text(text, **kwargs)}


def test_strong_insult_warns():
    assert "1" in ids("заткнись, идиот")


def test_rules_discussion_does_not_trigger_politics():
    assert "1.1" not in ids("По правилам политика и выборы запрещены")


def test_history_exception_does_not_auto_warn_politics():
    assert "1.1" not in ids("Историческое обсуждение выборов 1917 года")


def test_current_politics_is_detected():
    assert "1.1" in ids("Давайте устроим политический спор про выборы")


def test_doxxing_requires_personal_data_cue():
    assert "1.2" in ids("Вот его телефон +7 999 123 45 67")
    assert "1.2" not in ids("Код заказа 79991234567")


def test_ad_link_is_detected():
    assert "2.3" in ids("Подписывайтесь на мой канал https://t.me/example")


def test_irl_adult_caption_needs_media():
    text = "IRL порно с реальными людьми"
    assert "2.2" not in ids(text, has_media=False)
    assert "2.2" in ids(text, has_media=True)


def test_furry_adult_caption_is_not_irl_violation():
    assert "2.2" not in ids("фурри yiff порно арт", has_media=True)


def test_forwarded_channel_without_text_is_detected():
    assert "2.3" in ids("", forwarded_from_channel=True)


def test_long_rp_is_detected():
    text = "RP: *" + ("идёт по лесу и говорит с персонажем " * 120) + "*"
    assert "3.3" in ids(text)
