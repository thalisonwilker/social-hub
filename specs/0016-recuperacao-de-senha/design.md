---
name: design
description: Technical Design Doc da feature 0016 — recuperação de senha (SMTP nativo do Django, token com hash, limites no banco, link sem token nos logs). Puxe ao implementar ou revisar a feature.
alwaysApply: false
---

# Technical Design Doc — Recuperação de senha

> **Tier:** arquitetural (enxuto) · **Status:** aprovado
> **Autor:** Claude + Thalyson · **Data:** 2026-11-19
> Decisão difícil de reverter → [ADR-0017](../../docs/architecture/adr/0017-envio-de-e-mail-smtp-e-recuperacao-de-senha-com-token-em-hash.md).

## Contexto da funcionalidade
Sem envio de e-mail no projeto até aqui. A jornada precisa mandar o link e o aviso, sem revelar contas, com limites por IP e por conta e sem tokens em banco/logs.

## Goals / Non-goals
- **Goals:** pedido por e-mail com resposta genérica; link de uso único (30 min); redefinição com a política de senha atual; sessões antigas encerradas; aviso por e-mail.
- **Non-goals:** login automático, 2FA, fila de e-mails persistente, templates HTML elaborados (o e-mail é texto simples).

## Design proposto
1. **Pedido** — `GET/POST /recuperar-senha/`. Formulário com e-mail + `chave_idempotencia` (UUID gerado pela página, como no login). Ordem: campos → chave → repetição (mesma chave → mesma resposta, nada enviado) → limite por IP (5/15 min → 429) → registra o pedido → procura a conta (mesmo localizador do login) → limite por conta (1 e-mail/hora) → invalida links antigos, cria um token novo e agenda o e-mail. A resposta pública é sempre a mesma: redireciona (PRG) para `/recuperar-senha/` com a mensagem genérica.
2. **Envio fora da requisição** — o e-mail é enviado numa *thread* depois do `commit`, para o tempo de resposta não depender de haver conta (anti-enumeração por tempo). Em teste, o envio é síncrono (`ACCOUNTS_EMAIL_ASYNC=False`).
3. **Link** — `PUBLIC_BASE_URL` (ou a origem da requisição, validada por `ALLOWED_HOSTS`) + `/redefinir-senha/?token=<token>`. O GET com token **valida, guarda só o id do token na sessão e redireciona** para `/redefinir-senha/` sem query (o token sai da barra de endereço e do histórico; `Referrer-Policy: no-referrer`).
4. **Redefinição** — `GET/POST /redefinir-senha/` usa o id da sessão. No POST: valida as senhas (mesma política do cadastro: composição + validadores do Django), **consome o token com um UPDATE condicional** (`used_at IS NULL AND invalidated_at IS NULL AND expires_at > agora`; 1 linha = venceu a corrida), grava a senha com `set_password`, invalida os outros tokens da conta, remove as sessões da conta, envia o aviso e redireciona ao login com mensagem de sucesso. Não autentica.
5. **Token** — `secrets.token_urlsafe(32)` (256 bits); o banco guarda `sha256(token)`. Comparação pelo hash (consulta indexada).

## Cobertura dos 5 eixos
### 1. Tech stack
Django `django.core.mail` (SMTP nativo) e `secrets`/`hashlib` da biblioteca padrão. Sem dependência nova.
### 2. Arquitetura base
App `accounts`: `password_reset.py` (regras: token, limites, consumo), `emails.py` (montagem e envio dos dois e-mails), views finas, 2 modelos novos. Localizador de conta reaproveitado do `EmailBackend`; política de senha reaproveitada do cadastro.
### 3. Infra
`.env`: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`. Sem `EMAIL_HOST`: backend de **arquivo** em `var/emails/` (fora do git), nunca o console. *System check* avisa quando `DEBUG=False` e não há SMTP. O compose ganha o mesmo `.env` (já carrega).
### 4. Qualidade
Um teste por AC (`locmem` de e-mail no teste), corrida do consumo do token simulada, `assertLogs` sem token/senha/e-mail, expiração com relógio controlado.
### 5. Observabilidade
Log `apps.accounts.password_reset` com evento + IP + prefixo do hash do e-mail (como o login). Falha de SMTP vira `WARNING` sem o conteúdo do e-mail. Gunicorn já registra o caminho sem query (ADR-0008); o log do `runserver` ganha um filtro que remove a query string.

## Mapa de dependências
| Depende de | Para |
|---|---|
| `EmailBackend` (0014) | achar a conta pelo e-mail (username ou campo e-mail) |
| `PasswordCompositionValidator` + validadores do Django (0013) | política da nova senha |
| `login_throttle.hash_email`/`client_ip` (0014) | hash do e-mail e IP nos limites e logs |
| SMTP externo | entregar os e-mails |

## Alternativas consideradas
- **`PasswordResetView` nativo do Django** (token sem estado, HMAC do hash da senha): não é "uso único" até a senha mudar, não guarda hash no banco, não tem limite nem idempotência; adaptar daria mais código do que o desenho acima.
- **Token no fragmento (`#token`)**: some de todos os logs, mas exige JavaScript; o desenho escolhido já tira o token dos logs (gunicorn sem query + filtro no runserver) e da barra de endereço.
- **Provedor de e-mail por API**: conta externa e cliente próprio; SMTP cobre os provedores comuns sem código novo.
- **Envio síncrono**: mais simples, mas o tempo de resposta revelaria se a conta existe.

## Trade-offs e consequências
- Thread de envio: se o processo cair entre o `commit` e o envio, o e-mail se perde (a pessoa pede de novo após o limite). Aceito para não criar fila de e-mails agora.
- Limite por conta de 1 e-mail/hora: quem perder o e-mail espera até 1 hora.

## Riscos
- SMTP não configurado em produção → e-mails vão para arquivo no container; o *system check* avisa no deploy.
- IP atrás de proxy (mesma ressalva do ADR-0016).

## Roadmap da feature
Ver `tasks.md`.

## Questões em aberto
- Credenciais SMTP reais (provedor e remetente) — preencher no `.env` para o UAT.
