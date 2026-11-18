---
name: design
description: Technical Design Doc da feature 0010 — exclusão local (Remover do Hub) e na plataforma (Facebook e Threads), campo deleted_at, elegibilidade, erros e permissões. Puxe ao implementar ou revisar.
alwaysApply: false
---

# Technical Design Doc — Excluir publicações

> **Tier:** arquitetural · **Status:** aprovado · **Data:** 2026-11-18
> Decisão difícil de reverter → **ADR-0014** (task 1).

## Links e artefatos
| Artefato | Link |
|----------|------|
| Spec · Product · Domínio · Tasks | `./spec.md` · `./product.md` · `./domain.md` · `./tasks.md` |
| Docs da Meta | [Threads: Delete Posts](https://developers.facebook.com/documentation/threads/posts/delete-posts) · [Pages API: Posts](https://developers.facebook.com/documentation/pages-api/posts) · [blog Instagram (dez/2025)](https://developers.facebook.com/blog/post/2025/12/03/instragram-api-updates/) |

## Contexto
O histórico (`Publication` + `PublicationTarget`) é só de leitura e a imagem vive no volume `/media` (ADR-0005). O Facebook guarda `external_post_id` (`{page}_{post}`) e o Threads, o id da mídia: dá para apagar com as credenciais já guardadas.

## Goals / Non-goals
**Goals** — Remover do Hub; Apagar na plataforma (Facebook, Threads); por alvo e por publicação; confirmação; sem vazar segredos.
**Non-goals** — Instagram e WhatsApp, lixeira/desfazer, exclusão em massa na lista, edição de posts.

## Design proposto

### Modelo
`PublicationTarget.deleted_at` (`DateTimeField`, nulo). Migration 0008. Alvo apagado **continua `published`** (o status geral não muda); a tela mostra "Apagado na plataforma" e some o link.

### Elegibilidade (função pura `deletion.eligibility(target)`)
`apagável` ⇔ `status=published` ∧ `external_post_id≠""` ∧ `deleted_at` nulo ∧ conta conectada ∧ plataforma ∈ {facebook_page, threads}. Instagram e WhatsApp → `unsupported` ("Apague pelo app"). Conta desconectada ou em `needs_reauth` → `unavailable` com o motivo (a exclusão não chama a plataforma).

### Apagar na plataforma (`services/deletion.py`)
- **Facebook:** `DELETE /{post_id}` na Graph API com o **token da Página** no header (`GraphClient.delete_post`); sucesso = `{"success": true}`. Permissões já concedidas (`pages_manage_posts`).
- **Threads:** `DELETE /{media_id}` em `graph.threads.com` (`ThreadsClient.delete_media`), token renovado se devido (`ensure_fresh`); exige o escopo **`threads_delete`** (novo em `SCOPES`; contas antigas precisam **reconectar**) e tem limite de 100/dia.
- Síncrono na requisição (uma chamada curta, timeout 10 s). Sucesso ou "objeto inexistente" (Graph código 100 / subcódigo 33 e equivalente do Threads, **a confirmar no UAT**) → `deleted_at = agora`, atômico (`published` ∧ `deleted_at` nulo). Resposta desconhecida (timeout/interrompido) → **nada é gravado**, mensagem "não foi possível confirmar"; repetir é seguro (idempotente).
- Erros: token (102/190) → conta `needs_reauth`; permissão (10/200/220 ou "sem `threads_delete`") → "Reconecte o Threads para permitir apagar"; limite → mensagem de limite; rede → mensagem de rede. Nunca o texto cru da Meta.
- Apagar a publicação inteira: percorre os alvos apagáveis (ordem estável), resultado por alvo; os demais são listados com o motivo.

### Remover do Hub
`POST`, só dono, transação: apaga o(s) alvo(s) e a publicação; se era o último alvo, remove a publicação; depois apaga o arquivo da imagem (falha ao apagar arquivo é logada e não desfaz o banco). **Bloqueia** se algum alvo está `sending` (o worker o está enviando). Alvos `pending` saem junto (cancela o envio). A confirmação avisa que **o post continua na rede** (a menos que já tenha sido apagado) e, se há alvo Incerto, que ele pode estar publicado.

### Telas
Detalhe: por alvo, botões **Apagar na plataforma** e **Remover do Hub** (ou o texto "Apague pelo app" para Instagram/WhatsApp); no topo, **Apagar na plataforma (todos possíveis)** e **Remover do Hub**. Lista: **Remover do Hub** por linha. Todas as ações `POST` + CSRF + `data-confirm`.

## Cobertura dos 5 eixos
1. **Stack:** sem dependência nova.
2. **Arquitetura:** serviço `deletion` na camada de aplicação/serviços; clientes Graph/Threads ganham um método cada.
3. **Infra:** nenhuma; reversão: remover rotas e o campo (migration reversa).
4. **Qualidade:** APIs sempre mockadas; um teste por AC; matriz de elegibilidade vira casos.
5. **Observabilidade:** logs só `target_deleted platform=… result=…`, sem ids externos, texto, token nem corpo.

## Mapa de dependências
| Dependência | Descrição | Endpoint |
|-------------|-----------|----------|
| Graph API (Página) | apagar post | `DELETE /{page_post_id}` |
| Threads API | apagar post | `DELETE /{threads_media_id}` (escopo `threads_delete`, 100/dia) |

## Alternativas consideradas
| Alternativa | Decisão |
|-------------|---------|
| **Duas ações separadas** (escolhida) | Evita apagar o rastro antes de saber se o post saiu da rede |
| Uma ação que faz tudo | Rejeitada: se a plataforma falhar, o usuário perde o registro e o id do post |
| Novo status `deleted` no alvo | Rejeitada: espalha o estado pelas contagens/polling; `deleted_at` é um atributo |
| Exclusão assíncrona no worker | Rejeitada: é uma chamada curta e o usuário quer o resultado na hora |
| Instagram agora | Adiada: endpoint/permissão não documentados nas páginas que li |

## Riscos
| Risco | Mitigação |
|-------|-----------|
| Facebook só apagar posts do próprio app (não confirmado) | UAT; erro vira mensagem amigável |
| Contas do Threads sem `threads_delete` | Mensagem pedindo reconexão; README explica |
| Apagar por engano | Confirmação em toda ação; textos explícitos |
| Resposta desconhecida | Nunca marca apagado; repetir é idempotente |

## Roadmap
1 (MVP): tudo acima · 2: Instagram (quando a doc estiver clara), exclusão em massa.

## Questões em aberto
- [ ] Código/subcódigo de "objeto inexistente" no Facebook e no Threads (UAT).
- [ ] Facebook apaga posts não criados pelo app? (UAT)
