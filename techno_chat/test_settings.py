from .settings import *  # noqa


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MEDIA_ROOT = BASE_DIR / "test_media"

MIGRATION_MODULES = {
    "backoffice_engine": None,
}
