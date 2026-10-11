"""Keep every existing byte and append only missing default keys."""
from pathlib import Path
import re
import sys

def merge(existing: str, defaults: str) -> str:
    keys = set(re.findall(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', existing, re.M))
    additions = []
    for line in defaults.splitlines():
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
        if match and match[1] not in keys:
            additions.append(line)
            keys.add(match[1])
    if not additions:
        return existing
    return existing + ('' if existing.endswith('\n') else '\n') + '\n# New KiraBot defaults\n' + '\n'.join(additions) + '\n'

if __name__ == '__main__':
    old, new = map(Path, sys.argv[1:3])
    if old.exists():
        new.write_bytes(merge(old.read_bytes().decode('utf-8'), new.read_bytes().decode('utf-8')).encode('utf-8'))
