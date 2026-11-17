---
name: ADR-0009
description: Orçamento de tempo por requisição de publicação, para o envio nunca estourar o timeout do Gunicorn (complementa o ADR-0004).
alwaysApply: false
---

# ADR-0009: Orçamento de tempo por requisição de publicação

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
O ADR-0004 definiu envio síncrono em **lotes de 5 alvos**, com 30 s por upload e Gunicorn `--timeout 180` (5 × 30 s = 150 s). A feature `0005-threads-imagem` acrescenta, por alvo do Threads com imagem,
a **espera do container** (até 60 s). Com 5 alvos o pior caso passa de 180 s e o Gunicorn mataria o worker no meio de um envio, deixando alvos em `sending`.

## Decisão
- Cada requisição de envio tem um **orçamento de tempo** (`PUBLISH_REQUEST_BUDGET_SECONDS`, 150 s, menor que o `--timeout`).
- `send_pending` mede o tempo desde o início e **não inicia** um novo alvo se restarem **menos de 40 s**; os alvos restantes ficam `pending` e o usuário usa o **"Continuar envio"** já existente.
- A espera do container do Threads é **limitada** a `min(configurado, tempo restante − 25 s)`.
- O **lote de 5 continua como teto** de alvos por requisição; o **tempo passa a ser o limite real**.
- Alternativas descartadas: **fila/worker** (infra nova; é o caminho do agendamento), **reduzir o lote** (não resolve alvos lentos) e **aumentar o timeout** (adia o problema e prende workers).

## Consequências
- **+** Nenhuma requisição estoura o timeout; menos alvos presos em `sending`.
- **+** Sem infraestrutura nova; reaproveita "Continuar envio" e a retomada por container.
- **−** Um lote pode enviar menos de 5 alvos; o usuário pode precisar de mais um clique.
- **−** Os números (150, 40, 25 s) são heurísticos; ajustar com os tempos reais do UAT.
