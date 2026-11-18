---
name: domain
description: Modelo de domínio da feature 0010 — exclusão local e na plataforma, alvo apagado, elegibilidade. Puxe ao modelar ou implementar.
alwaysApply: false
---

# Domain Model — Excluir publicações

## Bounded Context
**Social** (app `social`), subdomínio **core**. Nenhum contexto novo.

## Linguagem ubíqua
| Termo | Definição | NÃO confundir com |
|-------|-----------|-------------------|
| Remover do Hub | Apagar a Publicação (ou um Alvo) do histórico do Hub e a imagem do volume. **Não** mexe no post da rede social. | Apagar na plataforma |
| Apagar na plataforma | Chamar a API da rede para excluir o post publicado de um Alvo (hoje: Facebook e Threads). Não remove o registro do Hub. | Remover do Hub |
| Alvo apagado | Alvo `published` com `deleted_at` preenchido: o post foi apagado na plataforma; o registro continua no histórico. | Alvo Falhou |
| Alvo apagável | Alvo `published`, com `external_post_id`, conta conectada e ativa, plataforma com exclusão suportada e ainda não apagado. | Alvo reenviável |
| Plataforma sem exclusão | Plataforma cuja exclusão o Hub não faz (Instagram, WhatsApp Status): mostra "Apague pelo app". | — |

> Termos a promover ao `docs/glossary.md`: Remover do Hub, Apagar na plataforma, Alvo apagado, Alvo apagável.

## Agregados, entidades e value objects
- **Agregado `Publication`** (raiz): `PublicationTarget` ganha `deleted_at` (nulo = não apagado).
  - **Invariantes:** `deleted_at` só existe em alvo `published`; o status geral da publicação continua derivado dos alvos (alvo apagado conta como `published`); remover um Alvo remove só ele, e remover o último remove a Publicação; remover a Publicação apaga o arquivo da imagem.
  - Fronteira de consistência: a remoção local é uma transação; a exclusão na plataforma é uma chamada externa seguida de uma atualização atômica do alvo.

## Eventos de domínio
| Evento | Disparado quando | Quem reage |
|--------|------------------|------------|
| `TargetDeletedOnPlatform` | a API confirma a exclusão (ou o objeto já não existe) | grava `deleted_at` |
| `PublicationRemoved` / `TargetRemoved` | o usuário remove do Hub | apaga linhas e arquivo |

## Relações com outros contextos
Anti-Corruption Layer existente (`services/meta.py`, `services/threads.py`): ganha `delete_post`/`delete_media` finos; o domínio não conhece a Graph API.
