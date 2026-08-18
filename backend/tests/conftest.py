import os

os.environ.setdefault("LOCAL_DEVELOPMENT", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATA_MODE", "test")
