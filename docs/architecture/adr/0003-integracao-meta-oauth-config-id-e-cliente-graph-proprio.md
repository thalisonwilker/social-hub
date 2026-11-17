---
name: ADR-0003
description: Integração com a Meta via OAuth com config_id (Login for Business) e cliente Graph próprio no app social.
alwaysApply: false
---

# ADR-0003: Integração Meta via OAuth `config_id` e cliente Graph próprio

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
O Social Hub vai integrar Facebook, Instagram e Threads. O app Meta está configurado com o caso de uso
*Gerenciar Páginas* e uma configuração de *Facebook Login for Business* (token de acesso do usuário), cujo
identificador (`config_id`) define as permissões. O app roda com workers síncronos do Gunicorn e poucas
dependências. A Graph API versiona e muda; o app Meta está na versão v27.0.

## Decisão
- Vamos autenticar com o **diálogo OAuth usando `config_id`**, fluxo `code` → token de usuário curto → token de longa
  duração → `/me/accounts` (tokens de Página), protegido por `state` de uso único.
- Vamos implementar um **cliente Graph próprio e fino** (`apps/social/services/meta.py`) com `requests`, que atua
  como **camada anticorrupção**: o resto do sistema não conhece os formatos da Meta.
- A **versão da Graph API** é fixada por `META_GRAPH_VERSION` (padrão `v27.0`) e enviada em toda chamada.
- Segredo e `code` vão em POST; tokens no header `Authorization: Bearer`; nunca em URL ou log.
- O token de usuário **não é persistido**.
- Alternativas descartadas: **OAuth clássico com `scope=`** (não é o fluxo do Login for Business configurado) e
  **SDK de terceiros** (dependência extra, menos controle da versão).

## Consequências
- **+** Poucas dependências, fluxo auditável e reutilizável por Instagram e Threads.
- **+** Atualizar a versão da Graph API é uma mudança de configuração, testável.
- **−** Mantemos o código do cliente e o tratamento de erros da Meta.
- **−** O comportamento exato do `config_id` será confirmado em um teste real com a Página de teste; se divergir,
  este ADR é substituído por outro.
