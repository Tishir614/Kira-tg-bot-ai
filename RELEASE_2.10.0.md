# KiraBot 2.10.0 Owner Stats

- `/stats` (статистика), `/stats неделя`, `/stats месяц` — owner/sudo only. Shows distinct active users and chats, messages, commands, top commands, AI ok/fail counts, AI latency (avg / p95 / max), request modes (chat/tech/analysis/creative), RP turns, image provider usage (horde/perchance/comfyui/fail).
- Storage: counters in `usage_stats.json` inside the data dir, 31 days kept. Users/chats are stored only as salted hashes (`USAGE_SALT`), message text is never stored. Recording failures never affect requests.
- masturbate and alcohol modules untouched.
