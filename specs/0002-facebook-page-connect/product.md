---
name: product
description: PRD-lite da feature 0002 — conectar uma Página do Facebook ao Social Hub.
alwaysApply: false
---

# Product — Conectar Página do Facebook

> **Tier:** arquitetural · **Status:** aprovado · **Dono:** Thalyson
> Responde: **por quê** e **para quem**.

## Problema
O Social Hub existe para centralizar a gestão de redes sociais, mas hoje não está ligado a nenhuma delas:
a dashboard exibe só dados demonstrativos e as páginas de *Contas conectadas*, *Publicações* e *Agenda* são
reservas. Sem uma conta real conectada, nenhuma funcionalidade seguinte (insights, publicação, agendamento)
pode existir. A Meta exige um fluxo OAuth e tokens de acesso por Página, o que precisa ser desenhado com
segurança desde o início.

## Para quem
Usuários do Social Hub que administram uma ou mais Páginas do Facebook (inicialmente o próprio dono do
projeto, em modo Desenvolvimento do app Meta). Uso esporádico: a conexão é feita uma vez e revisitada
quando o token expira ou a pessoa quer trocar de Página.

## Resultado esperado / métrica de sucesso
Um usuário autenticado consegue conectar sua conta Meta, escolher uma ou mais Páginas que administra e vê-las
listadas como conectadas; consegue desconectá-las. Os tokens ficam protegidos e nunca aparecem em tela ou log.
- Métrica: Páginas conectadas com sucesso a partir do fluxo (fluxo completo em ≤ 1 minuto).
- Baseline: 0 contas reais conectadas → Alvo: 1 Página de teste conectada ponta a ponta.

## Goals
- Fluxo OAuth com a Meta (Facebook Login for Business, `config_id`, token de usuário) protegido por `state`.
- Tela de **seleção multi-Página** após o login: o usuário marca uma ou várias Páginas de uma vez (com "marcar todas"), em vez de conectá-las uma a uma.
- Obter o token de cada Página escolhida e armazená-lo **criptografado** em repouso (Fernet, chave no `.env`).
- Deixar a base para a publicação futura escolher **em qual das Páginas conectadas** publicar.
- Modelo por usuário: cada usuário conecta sua conta Meta e escolhe uma ou mais Páginas; cada Página vira uma
  "conta social" própria, reutilizável por Instagram e Threads no futuro.
- Tela *Contas conectadas* funcional: conectar, listar (nome, status) e desconectar.
- Dashboard passa a refletir o Facebook como "Conectado" quando houver Página ativa.
- Camada de serviço da Graph API no app `social`, com versão da API configurável.

## Non-goals
- Publicação de conteúdo e agendamento.
- Insights/métricas reais (`read_insights`) — a dashboard continua com dados demonstrativos nesta etapa.
- Instagram e Threads (podem exigir apps Meta separados; entram em features próprias).
- App Review / Business Verification da Meta e modo Live (uso apenas com contas com função no app).
- Webhooks.
- Renovação automática em background de tokens (tratamos expiração/revogação pedindo reconexão).

## Riscos / premissas
- **Premissa:** a configuração Meta está pronta (caso de uso *Gerenciar Páginas*, permissões `pages_show_list`,
  `pages_read_engagement`, `pages_manage_posts`, `read_insights` e configuração de login com `config_id`).
- **Premissa:** em modo Desenvolvimento só contas com função no app conseguem autorizar; aceitável nesta etapa.
- **Risco:** a Graph API muda de versão e de comportamento; mitigado fixando `META_GRAPH_VERSION`.
- **Risco:** vazamento do SQLite ou do `.env` expõe acesso às Páginas; mitigado com criptografia, chave separada
  e ausência de tokens em logs/templates.
- **Risco:** redirect URI diferente entre ambientes (localhost × domínio HTTPS) quebra o login; deve ser
  configurável por variável de ambiente.
