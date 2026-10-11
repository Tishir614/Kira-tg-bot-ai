"""Remove common credentials from diagnostic messages."""
import os
import re

def redact(value: object) -> str:
    text = str(value)
    for key, secret in os.environ.items():
        if any(part in key.upper() for part in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'API_HASH')) and len(secret) >= 8:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b', '[REDACTED]', text)
    text = re.sub(r'(?i)(bearer\s+)[\w.~/+=-]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)([?&](?:key|token|api_key|access_token)=)[^&\s]+', r'\1[REDACTED]', text)
    return text
