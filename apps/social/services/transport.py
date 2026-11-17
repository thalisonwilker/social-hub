"""Classificação de erros de transporte (spec 0007, AC-6): o Hub precisa saber se a requisição **chegou** ao servidor.

- `network`     — nunca chegou (DNS, conexão recusada, TLS, proxy, URL inválida): o servidor NÃO processou; é falha certa.
- `timeout`     — a requisição foi enviada e a resposta não veio dentro do prazo de leitura.
- `interrupted` — conexão cortada depois de enviar (ou sem detalhe suficiente): o servidor PODE ter processado.

`timeout`/`interrupted` numa chamada **com efeito** (a que cria o post) tornam o alvo Incerto. Na dúvida, `interrupted`:
tratar como falha certa algo que publicou levaria a reenviar às cegas. Nada do texto da exceção (costuma trazer URL/token) sai daqui.
"""
import requests
from urllib3.exceptions import (
    ConnectTimeoutError,
    NewConnectionError,
    ProxyError as Urllib3ProxyError,
    SSLError as Urllib3SSLError,
)

try:  # urllib3 >= 2
    from urllib3.exceptions import NameResolutionError
except ImportError:  # pragma: no cover
    NameResolutionError = NewConnectionError

NEVER_REACHED = "network"
READ_TIMEOUT = "timeout"
INTERRUPTED = "interrupted"

_CONNECT_STAGE = (NewConnectionError, NameResolutionError, ConnectTimeoutError, Urllib3SSLError, Urllib3ProxyError)


def classify_request_error(exc: BaseException) -> str:
    """Devolve `network`, `timeout` ou `interrupted` para uma exceção do `requests`."""
    if isinstance(exc, requests.exceptions.ConnectTimeout):  # subclasse de ConnectionError e de Timeout: vem primeiro
        return NEVER_REACHED
    if isinstance(exc, (requests.exceptions.SSLError, requests.exceptions.ProxyError)):
        return NEVER_REACHED
    if isinstance(exc, requests.exceptions.Timeout):
        return READ_TIMEOUT
    if isinstance(exc, requests.exceptions.ConnectionError):
        inner = exc.args[0] if exc.args else None
        reason = getattr(inner, "reason", inner)  # MaxRetryError.reason ou a própria exceção interna
        if isinstance(reason, _CONNECT_STAGE):
            return NEVER_REACHED
        return INTERRUPTED
    if isinstance(exc, (requests.exceptions.ChunkedEncodingError, requests.exceptions.ContentDecodingError)):
        return INTERRUPTED
    return NEVER_REACHED  # URL inválida, esquema ausente etc.: nada foi enviado
