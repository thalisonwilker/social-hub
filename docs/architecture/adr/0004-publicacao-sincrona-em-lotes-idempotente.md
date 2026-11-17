---
name: ADR-0004
description: Publicação na Meta síncrona, em lotes de 5, idempotente por claim atômico por alvo.
alwaysApply: false
---

# ADR-0004: Publicação síncrona em lotes, idempotente por claim atômico

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A feature `0003-publicar-no-facebook` publica uma imagem com texto em várias Páginas. Cada chamada à Graph API envia o
arquivo e pode levar segundos. O ambiente é Gunicorn síncrono com timeout padrão de 30 s, SQLite e **sem** fila/worker.
Publicar duas vezes na mesma Página é um erro visível e irreversível pelo Hub (não há exclusão nesta etapa).

## Decisão
- O envio é **síncrono dentro da requisição**, em **lotes de até 5 alvos** (`PUBLISH_BATCH_SIZE`). Alvos restantes ficam
  `pending`; o usuário usa "Continuar envio". O mesmo botão repete só os que falharam.
- Cada **alvo** (publicação × Página) é **reivindicado atomicamente** antes da chamada:
  `UPDATE … SET status='sending' WHERE status IN ('pending','failed') OR (status='sending' AND last_attempt_at < agora−5 min)`;
  só `rowcount == 1` autoriza o envio. Alvo `published` nunca é reenviado.
- Timeout por chamada de upload de 30 s e **Gunicorn `--timeout 180`** (5 × 30 s = 150 s no pior caso).
- **Janela residual aceita:** queda do processo após a Meta publicar e antes de gravar `published` pode gerar post duplicado
  após a recuperação (5 min). Tratamento melhor rastreado na issue #1.
- Alternativas descartadas: **fila/worker** (infra desproporcional agora; entra com o agendamento) e **uma requisição única
  para todas as Páginas** (estoura o timeout).

## Consequências
- **+** Sem infra nova; cliques/abas duplicados não duplicam posts; retry por Página é simples.
- **+** Timeout limitado e previsível.
- **−** O usuário espera durante o envio; muitas Páginas exigem mais de um clique.
- **−** Janela residual de duplicidade (issue #1). O agendamento futuro substituirá este modelo por fila.
