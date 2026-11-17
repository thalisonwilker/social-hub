"""Validações de entrada da integração com a Evolution (spec 0006)."""
import re

# Nome da instância vai NA ROTA da Evolution: só caracteres seguros (sem `/`, `.`, `?`, `#`, `%`, espaço).
INSTANCE_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def is_valid_instance_name(name) -> bool:
    return isinstance(name, str) and INSTANCE_NAME_RE.fullmatch(name) is not None


def clean_instance_key(raw) -> str:
    """Remove espaços e quebras de linha comuns ao colar a chave; vazio se não sobrar nada."""
    return re.sub(r"\s+", "", raw or "")
