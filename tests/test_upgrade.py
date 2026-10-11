import importlib.util
from pathlib import Path
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('safe_upgrade', ROOT / 'tools/safe_upgrade.py')
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)

def release(tmp_path, extra=None):
    archive = tmp_path / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for p in ('setup.sh', 'upgrade.sh', 'tools/safe_upgrade.py', 'pyproject.toml', 'bot/__init__.py'):
            z.write(ROOT / p, 'release/' + p)
        z.writestr('release/.env', 'TOKEN=should-never-install')
        z.writestr('release/static/db', 'should-never-install')
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return archive

def target(tmp_path):
    p = tmp_path / 'installed'; p.mkdir()
    (p / '.env').write_bytes(b'# custom\r\nTOKEN=fixture\r\nCUSTOM=x\r\n')
    (p / 'static').mkdir(); (p / 'static/db').write_bytes(b'database\x00')
    (p / 'bot').mkdir(); (p / 'bot/old.py').write_text('old')
    return p

def test_preserve_env_static_backup_and_extra(tmp_path):
    p = target(tmp_path)
    (p / 'custom.txt').write_text('keep')
    before = (p / '.env').read_bytes()
    backup = up.install(release(tmp_path), p)
    assert (p / '.env').read_bytes() == before
    assert (p / 'static/db').read_bytes() == b'database\x00'
    assert (p / 'custom.txt').read_text() == 'keep'
    assert (backup / 'bot/old.py').read_text() == 'old'
    assert (backup / '.env').read_bytes() == before

@pytest.mark.parametrize('extra', [{'../escape': 'x'}, {'release/broken.py': 'def ('}, {'release/fail.sh': 'if then'}])
def test_invalid_release_leaves_old_code(tmp_path, extra):
    p = target(tmp_path)
    with pytest.raises(Exception): up.install(release(tmp_path, extra), p)
    assert (p / 'bot/old.py').read_text() == 'old'

def test_copy_failure_rolls_back(tmp_path, monkeypatch):
    p = target(tmp_path)
    original = up.shutil.copytree
    def fail(src, dst, *a, **kw):
        if Path(src).name == 'bot' and 'kira-stage-' in str(src):
            raise OSError('simulated disk failure')
        return original(src, dst, *a, **kw)
    monkeypatch.setattr(up.shutil, 'copytree', fail)
    with pytest.raises(OSError): up.install(release(tmp_path), p)
    assert (p / 'bot/old.py').read_text() == 'old'
    assert (p / 'static/db').read_bytes() == b'database\x00'
