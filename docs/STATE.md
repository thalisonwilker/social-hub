---
name: STATE
description: Memória de trabalho volátil — onde paramos, próximo passo, bloqueios.
alwaysApply: true
---

# STATE — Memória viva do projeto

> Memória de trabalho **entre sessões** (humanos e agentes). É **volátil**: atualizada o tempo
> todo. Diferente do **ADR** (decisão durável e imutável). Decisão estrutural → ADR; estado do
> trabalho → aqui. Atualize ao **pausar/encerrar**; leia ao **retomar**. Use a skill `/handoff`.

**Última atualização:** 2026-11-17 por Thalyson

## Em andamento / próximo passo
> O que está aberto agora e a **próxima ação concreta** (não "continuar a feature" — diga o passo).
- Feature ativa: `specs/0002-facebook-page-connect/` — implementada (tasks 1–11 feitas); falta **UAT real**.
- Próximo passo: rodar o roteiro de UAT com a Página de teste em http://localhost:8080 (conectar → selecionar várias →
  verificar → desconectar → reconectar). Se o login com `config_id` se comportar diferente do previsto, ajustar o fluxo
  e revisar o ADR-0003. Depois, marcar a spec como `implementado` e abrir a próxima feature (insights ou publicação).

## Decisões recentes
> Resumo cronológico. Se for difícil de reverter, vire um ADR e linke aqui.
- 2026-11-17: tokens de Página criptografados com Fernet, chave no `.env` — [ADR-0002](architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md)
- 2026-11-17: OAuth com `config_id` + cliente Graph próprio no app `social`; Graph API fixada em v27.0 — [ADR-0003](architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md)
- 2026-11-17: Seleção multi-Página numa tela do Hub; Páginas pendentes ficam na sessão, com tokens cifrados (TTL 10 min).

## Bloqueios
- [ ] UAT real da feature 0002 depende de você autorizar o app no Facebook com a Página de teste (login manual).

## Ideias adiadas / backlog técnico
- Cofre de segredos (Vault/KMS) para a chave Fernet → quando houver mais de um ambiente ou time.
- Limitação de tentativas de login (ex.: django-axes) → antes de expor o sistema publicamente.
- Lint e análise estática na CI (ruff, SAST) → ao configurar a esteira de CI.
- Renovação automática de tokens e webhooks → junto com publicação/agendamento.

## Todos soltos
- [ ] Fazer backup da `META_TOKEN_ENCRYPTION_KEY` fora do repositório (perdê-la exige reconectar as Páginas).
- [ ] Cadastrar política de privacidade e exclusão de dados no app Meta antes do modo Live / App Review.
