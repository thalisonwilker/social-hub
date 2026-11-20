"""Filtros de log (spec 0016, AC-14)."""

import logging
import re

_QUERY = re.compile(r"\?[^\s\"]*")


class StripQueryString(logging.Filter):
    """Remove a query string das linhas de acesso do `runserver` (ex.: `?token=` do link de redefinição).

    O gunicorn já registra só o caminho (docker/gunicorn.conf.py, ADR-0008).
    """

    def filter(self, record):
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(_QUERY.sub("", a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = _QUERY.sub("", record.msg)
        return True
