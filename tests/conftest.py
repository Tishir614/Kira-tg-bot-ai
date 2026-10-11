"""Test environment: fake credentials and an isolated data dir, set before any bot import."""
import os
import tempfile

os.environ.setdefault("TOKEN", "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("OWNER_ID", "1")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="kira-test-data-"))
