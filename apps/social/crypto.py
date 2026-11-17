"""Criptografia dos tokens da Meta em repouso (Fernet / MultiFernet). Ver ADR-0002."""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from .conf import encryption_keys


class TokenCryptoError(Exception):
    """Falha ao criptografar/descriptografar. Nunca carrega o token nem a chave."""


def _fernet() -> MultiFernet:
    keys = encryption_keys()
    if not keys:
        raise TokenCryptoError("META_TOKEN_ENCRYPTION_KEY não configurada.")
    try:
        # A primeira chave criptografa; todas descriptografam (rotação).
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError):
        raise TokenCryptoError("META_TOKEN_ENCRYPTION_KEY inválida.") from None


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        raise TokenCryptoError("Token ilegível com a(s) chave(s) atual(is).") from None
