"""Regras de texto do Threads (limite de 500 com emoji por bytes UTF-8 e máximo de 5 links únicos)."""
import re
import unicodedata
from urllib.parse import urlsplit

THREADS_MAX_WEIGHT = 500
THREADS_MAX_LINKS = 5

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}>\"'"


def threads_weight(text: str) -> int:
    """Peso conservador do texto para o limite de 500 do Threads.

    A Meta conta emoji por bytes UTF-8. Sem grapheme-splitter, aproximamos: caractere fora do BMP vale 4,
    símbolo (categoria `So`), VS16 e ZWJ valem 3 (bytes de cada componente) e o resto vale 1.
    Nunca subestima emoji comuns; a Meta tem a palavra final (erro tratado no envio).
    """
    weight = 0
    for char in text:
        if ord(char) > 0xFFFF:
            weight += 4
        elif char in ("‍", "️") or unicodedata.category(char) == "So":
            weight += 3
        else:
            weight += 1
    return weight


def _normalize(url: str) -> str:
    url = url.rstrip(_TRAILING)
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}{query}"


def count_unique_links(text: str) -> int:
    """Quantidade de URLs http(s) únicas no texto (repetições contam uma vez)."""
    return len({_normalize(match) for match in _URL_RE.findall(text)})
