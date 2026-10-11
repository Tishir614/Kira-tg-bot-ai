# KiraBot 2.7.0

## Added
- Long-term conversation memory: messages that fall out of the 24-message window are folded in the background into a per-chat summary (`conversation_summaries` table) and fed back into the prompt as context. `/forget` wipes it too.
- Automatic web grounding (`bot/web_context.py`): questions about fresh data (today, rates, prices, news, "кто выиграл"...) get up to 5 search snippets added as untrusted data before the model answers. 7 s timeout; any failure silently falls back to a normal answer. Not used in 18+ mode.

## Untouched
- masturbate and alcohol modules.
