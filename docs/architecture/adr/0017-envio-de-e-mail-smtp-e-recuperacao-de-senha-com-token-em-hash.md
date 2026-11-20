---
name: ADR-0017
description: Envio de e-mail pelo SMTP nativo do Django (arquivo no dev) e recuperação de senha com token de uso único guardado como hash, limites no banco e link sem token nos logs.
alwaysApply: false
---

# ADR-0017: Envio de e-mail por SMTP e recuperação de senha com token em hash

- **Status:** aceito
- **Data:** 2026-11-19
- **Decisores:** Thalyson

## Contexto
A recuperação de senha (spec 0016) é a primeira funcionalidade que envia e-mail. O app roda em Docker com SQLite, 2 workers do gunicorn e sem fila de e-mails. Requisitos: token de uso único com 30 min, só hash no banco, sem enumeração de contas, limites por IP e por conta, nada sensível em logs.

## Decisão
- **E-mail:** `django.core.mail` com SMTP configurado no `.env`; sem SMTP, backend de **arquivo** em `var/emails/` (nunca console). Envio numa thread após o `commit`.
- **Token:** `secrets.token_urlsafe(32)`; banco guarda `sha256`. No máximo um válido por conta; consumo por UPDATE condicional; trocar a senha invalida todos.
- **Link:** `?token=` só no primeiro GET, que guarda o id do token na sessão e redireciona para a URL limpa; gunicorn já loga sem query (ADR-0008) e o runserver ganha filtro.
- **Limites (no banco, como o ADR-0016):** 5 pedidos por IP em 15 min → 429; 1 e-mail por conta por hora (silencioso, mesma resposta pública).
- **Sessões:** após a troca, as sessões da conta são apagadas.
- **Descartado:** `PasswordResetView` nativo (sem uso único real, sem hash/limites), token no fragmento (exige JS), provedor por API (conta externa), envio síncrono (vaza existência pelo tempo).

## Consequências
- Primeira dependência de serviço externo (SMTP); sem ele, os e-mails ficam em arquivo.
- E-mail pode se perder se o processo cair antes do envio (sem fila).
- Novos modelos `PasswordResetRequest` e `PasswordResetToken`; retenção de 24 h para pedidos e tokens vencidos.
