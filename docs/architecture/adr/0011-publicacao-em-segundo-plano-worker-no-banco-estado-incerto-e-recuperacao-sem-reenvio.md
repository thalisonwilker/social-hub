---
name: ADR-0011
description: Publicação em segundo plano — worker no próprio banco (SQLite como fila), estado Incerto resolvido pelo usuário e recuperação sem reenvio automático; substitui parcialmente os ADRs 0004 e 0009.
alwaysApply: false
---

# ADR-0011: Publicação em segundo plano — worker no banco, estado Incerto e recuperação sem reenvio

- **Status:** aceito (substitui parcialmente o [ADR-0004](0004-publicacao-sincrona-em-lotes-idempotente.md) e o [ADR-0009](0009-orcamento-de-tempo-por-requisicao-de-publicacao.md))
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
O envio rodava **dentro da requisição** (`send_pending`): lote de 5, orçamento de 150 s (ADR-0009) e recuperação de um alvo `sending` preso após 5 min (ADR-0004).
Três problemas reais apareceram:
1. **Duplicidade.** No UAT do WhatsApp (0006) o Hub deu timeout aos 60 s, marcou "Falhou" e ofereceu reenviar, mas a Evolution **publicou depois**; o reenvio duplicou o Status para ~2265 contatos. A recuperação de `sending` após 5 min tinha o mesmo risco no Facebook e no Threads (issue #1).
2. **Teto de tempo** (issue #4): o que não cabia no orçamento exigia "Continuar envio".
3. **Sem agendamento:** não havia quem enviasse "mais tarde".
A infraestrutura é pequena: **uma instância**, **SQLite em WAL** (`timeout=20`, `IMMEDIATE`) e `docker compose` com um serviço.

## Decisão
- **Worker no próprio banco.** Os alvos `pending` são a fila (FIFO por id), sem tabela de jobs. Um processo `manage.py run_worker`, em um **segundo container** (mesma imagem e mesmos volumes), reivindica **um alvo por vez** com o claim atômico (`UPDATE … WHERE status='pending'`) e o envia pelo despacho da plataforma, **sem orçamento por requisição** (usa o timeout de cada chamada).
- **Estado `uncertain` ("Incerto").** Quando a **chamada com efeito** (upload do Facebook, `threads_publish`, `sendStatus`) foi enviada e a resposta se perdeu (`timeout`/`interrupted`), ou veio inválida depois de aceita, o Hub **não sabe** se publicou. O alvo vira `uncertain` e **nunca** volta sozinho para a fila; o usuário escolhe **Já foi publicado** (vira `published`, sem link) ou **Reenviar** (volta a `pending`, assumindo o risco). Falhas que nunca chegaram ao servidor (DNS, recusada, TLS) e respostas de erro da plataforma continuam `failed`. Os clientes passam a distinguir `network` × `timeout` × `interrupted`.
- **Recuperação sem reenvio (fecha a issue #1).** Só `pending` é reivindicado. Na **partida** do worker todo `sending` vira `uncertain` (`worker_restart`) — com um único worker nenhum tem dono vivo — e um `sending` além de `PUBLISH_SENDING_STALE_SECONDS` (900 s) vira `uncertain` (`stale`). A recuperação automática de 5 min deixa de existir.
- **Modo de publicação.** `PUBLISH_MODE=worker` (padrão em produção): Publicar só enfileira e responde na hora. `PUBLISH_MODE=inline` (padrão em dev e na suíte): envia na requisição como antes (lote, orçamento do ADR-0009), com as mesmas regras de incerteza. Trocar o modo não exige migração; um test runner (`InlinePublishRunner`) mantém a suíte em `inline`.
- **Progresso e operação.** Polling de 3 s no detalhe (JSON mínimo: ids, estados, contagens, `worker.active`, `done`), que recarrega a página quando algo muda. O worker grava um **heartbeat** (`WorkerHeartbeat`) a cada ciclo; a tela avisa se há alvo em andamento e nenhum worker ativo (> 180 s sem batida); `worker_health` serve de healthcheck do compose. SIGTERM termina o alvo atual e sai.
- **Alternativas descartadas:** **Celery + Redis** (Redis, broker e operação desproporcionais para uma instância; o agendamento pode usar esta mesma fila); **thread dentro do Gunicorn** (morre com o worker e não serve para tarefas longas); **reenvio automático** (duplica quando a plataforma conclui depois do timeout); **consultar a plataforma antes de reenviar** (cada API é diferente; fica como evolução do estado Incerto).

## Consequências
- **+** O clique em Publicar responde na hora, sem depender de quantos destinos nem do tamanho da audiência.
- **+** Nenhum post é reenviado sem decisão do usuário; a janela de duplicidade da issue #1 fecha.
- **+** Sem infraestrutura nova além de um container; a mesma fila servirá ao agendamento.
- **−** **Um worker sequencial:** um Status de 100 s atrasa os seguintes; mais de um worker exigiria redesenhar a recuperação da partida.
- **−** Se o worker parar, nada é enviado (mitigado por heartbeat, aviso na tela, healthcheck e `restart: unless-stopped`).
- **−** O estado Incerto pede uma decisão do usuário; sem consulta à plataforma ela é manual.
- **−** Dois modos de envio para manter; `inline` fica como padrão de dev/testes.
- **−** O SQLite recebe escritas de dois processos: transações curtas, WAL e `database is locked` tratado como "tenta no próximo ciclo".
