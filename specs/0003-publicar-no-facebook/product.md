---
name: product
description: PRD-lite da feature 0003 — publicar texto + imagem em uma ou várias Páginas do Facebook.
alwaysApply: false
---

# Product — Publicar no Facebook (texto + imagem, várias Páginas)

> **Tier:** arquitetural · **Status:** rascunho · **Dono:** Thalyson
> Responde: **por quê** e **para quem**. Depende da [0002](../0002-facebook-page-connect/spec.md) (contas conectadas).

## Problema
Com as Páginas conectadas, o Social Hub ainda não publica nada: a página *Publicações* é só uma reserva. Quem gerencia
mais de uma Página precisa abrir cada uma no Facebook e repetir o mesmo post (texto + imagem) uma a uma, o que é lento e
sujeito a erro. O valor central do Social Hub — publicar uma vez e escolher onde — ainda não existe.

## Para quem
Usuários do Social Hub com uma ou mais Páginas do Facebook conectadas (inicialmente o próprio dono do projeto, com
Páginas de teste). Uso recorrente: várias publicações por semana.

## Resultado esperado / métrica de sucesso
O usuário escreve um texto, anexa **uma imagem**, marca **uma ou mais Páginas** e publica de uma vez, vendo o resultado
de cada Página (sucesso com link do post, ou o motivo do erro) e podendo repetir só as que falharam.
- Métrica: tempo para publicar o mesmo conteúdo em N Páginas.
- Baseline: manual no Facebook (≈ 1–2 min por Página) → Alvo: ≤ 1 min no total para 2 Páginas de teste.

## Goals
- Formulário de nova publicação: **texto (legenda) + 1 imagem** (JPG/PNG, tamanho limitado) e **seleção de uma ou mais
  Páginas** conectadas e ativas (com "Marcar todas").
- **Publicar agora**: envio à Graph API Página por Página, **resultado individual** (publicado / falhou + motivo).
- **Tentar novamente** apenas as Páginas que falharam, sem duplicar as que já publicaram.
- Histórico em *Publicações*: lista das publicações com data, texto resumido, miniatura e status por Página
  (link para o post no Facebook quando publicado).
- Páginas com "Reconexão necessária" são sinalizadas e não podem ser alvo até reconectar; falha de token durante o
  envio marca a conta como `needs_reauth`.

## Non-goals
- Agendamento e fila de publicações (feature futura).
- Rascunhos, edição ou exclusão do post já publicado no Facebook.
- Mais de uma imagem, vídeo, publicação só de texto (a imagem é obrigatória nesta entrega).
- Instagram e Threads.
- Execução em background (workers/fila): o envio é síncrono na requisição.
- Insights/métricas do post.
- Armazenamento externo de mídia (S3 etc.).

## Riscos / premissas
- **Premissa:** `pages_manage_posts` já está liberada no app Meta (modo Desenvolvimento) para contas com função no app.
- **Premissa:** o envio por várias Páginas cabe numa requisição síncrona (limite prático de poucas Páginas; timeout de 10 s por chamada).
- **Risco:** publicar de verdade em Páginas reais durante testes → usar Páginas de teste; o design deve deixar claro o que será publicado antes de enviar.
- **Risco:** reenvio/duplo clique gera post duplicado → o design precisa ser idempotente por Página (publicação × Página tem no máximo um post).
- **Risco:** token expirado/revogado no meio do envio → falha parcial; tratar por Página e marcar `needs_reauth`.
- **Risco:** upload de arquivo malicioso ou muito grande → validar tipo real, tamanho e dimensões; nunca servir como executável.
- **Risco:** imagens ficam só no volume local → backup do volume `/media`; perder o volume afeta o histórico (não os posts já publicados).
