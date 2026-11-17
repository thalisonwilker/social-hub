"""Desenvolvimento local: DEBUG ligado e valores padrão permissivos."""
from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env_list

DEBUG = True

if not SECRET_KEY:
    SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
