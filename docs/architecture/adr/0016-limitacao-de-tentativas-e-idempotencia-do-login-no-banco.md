---
name: ADR-0016
description: Limitação de tentativas e idempotência do login guardadas no banco (tabela de tentativas com hash do e-mail), sem cache compartilhado nem dependência nova.
alwaysApply: false
---

# ADR-0016: Limitação de tentativas e idempotência do login no banco

- **Status:** aceito
- **Data:** 2026-11-19
- **Decisores:** Thalyson

## Contexto
A jornada de login (spec 0014) precisa limitar tentativas (força bruta) e tratar requisições
repetidas com a mesma chave de idempotência sem criar sessões extras. O app roda com **2 workers
do gunicorn**, banco **SQLite** e **nenhum cache compartilhado** (o `LocMemCache` padrão é por
processo): contadores em cache local deixariam cada worker com sua própria contagem.

## Decisão
- Uma tabela `LoginAttempt` (app `accounts`) guarda **uma linha por tentativa de credencial**:
  chave de idempotência (UUID, **única**), `email_hash` (HMAC-SHA256 do e-mail normalizado com a
  `SECRET_KEY`), IP (`REMOTE_ADDR`), resultado (`succeeded`) e data.
- **Limite:** 5 falhas por `email_hash` desde o último sucesso dele, ou 20 falhas por IP, numa
  janela de 15 min → HTTP 429 com `Retry-After`, sem verificar a senha.
- **Idempotência:** a linha é gravada com a chave única **antes** de `login()`; repetições leem o
  resultado gravado e nunca criam sessão. Nada de sessão/token é persistido.
- **Retenção:** linhas com mais de 24 h são apagadas a cada novo POST de login.
- **Descartado:** `django-axes`/`django-ratelimit` (dependência nova para pouco código),
  `DatabaseCache` do Django (contadores opacos, outra tabela de infraestrutura e sem a regra
  "desde o último sucesso"), Redis (serviço novo só para isso).

## Consequências
- Funciona igual com qualquer número de workers no mesmo banco; regra explícita e testável.
- Uma escrita por tentativa no SQLite (volume baixo neste app).
- O e-mail não fica em claro; trocar a `SECRET_KEY` "zera" a contagem por e-mail (aceitável).
- **IP atrás de proxy:** com proxy reverso, `REMOTE_ADDR` é o do proxy e o limite por IP vale para
  todos juntos. Ao publicar atrás de proxy confiável, ler o IP do cabeçalho que o proxy garante.
- O `/admin/login/` do Django não passa por esta limitação (fora do escopo da spec 0014).
