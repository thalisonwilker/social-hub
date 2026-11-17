"""Configuração do Gunicorn do Social Hub.

O log de acesso registra o método e o CAMINHO (`%(U)s`), sem a query string: o token da URL pública da
imagem (spec 0005, ADR-0008) viaja na query e não pode ir para os logs.
"""
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s "%(a)s"'
