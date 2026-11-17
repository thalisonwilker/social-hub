---
name: product
description: PRD-lite da feature 0007 — publicar em segundo plano (worker no banco, claim atômico, estado "Incerto") para o envio não prender a requisição HTTP nem duplicar posts.
alwaysApply: false
---

# Product — Publicação em segundo plano (worker, idempotência e progresso)

> **Tier:** arquitetural · **Status:** rascunho · **Dono:** Thalyson
> Responde: **por quê** e **para quem**. Muda o caminho de envio das [0003](../0003-publicar-no-facebook/spec.md), [0004](../0004-threads-conectar-e-publicar/spec.md),
> [0005](../0005-threads-imagem/spec.md) e [0006](../0006-whatsapp-status/spec.md); respeita o [ADR-0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md) (claim atômico) e substitui, para o caminho HTTP, o [ADR-0009](../../docs/architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md) (orçamento por requisição).

## Problema
Hoje a requisição "Publicar agora" **fica aberta enquanto envia** (até 150 s) e só então responde. Isso causa três dores reais, já vividas:
1. **Duplicidade.** No UAT do WhatsApp o Hub deu *timeout* aos 60 s, marcou **Falhou** e ofereceu "Tentar novamente", mas a Evolution **publicou depois**: o reenvio **duplicou o Status para ~2265 contatos**. O mesmo risco existe no Facebook/Threads quando um alvo `sending` fica preso e é recuperado após 5 min ([issue #1](https://github.com/thalisonwilker/social-hub/issues/1)).
2. **Teto de tempo.** Com o orçamento por requisição, o que não coube vira `pending` e exige **Continuar envio** ([issue #4](https://github.com/thalisonwilker/social-hub/issues/4)); imagem no Threads (até 60 s de espera) e Status com muitos contatos (> 60 s) esbarram nele.
3. **Sem agendamento.** A página Agenda é só um espaço reservado porque não existe quem envie "mais tarde".

## Para quem
O operador do Social Hub, que publica em várias plataformas de uma vez (Facebook, Threads, WhatsApp) e precisa **confiar** no resultado de cada destino sem ficar de olho na tela nem reenviar às cegas.

## Resultado esperado / métrica de sucesso
Clicar em **Publicar** responde **na hora**; o envio acontece fora da requisição e a tela mostra o andamento sozinha. Quando o resultado de um envio é **desconhecido**, o Hub **não reenvia sozinho** e pede a sua decisão.
- Métrica 1: tempo até a tela responder após "Publicar".
  - Baseline: até 150 s (depende dos destinos) → Alvo: < 2 s, independente de quantos destinos ou do tamanho da audiência.
- Métrica 2: reenvios automáticos de um alvo cujo resultado era incerto.
  - Baseline: possível (alvo `sending` preso é reenviado após 5 min; timeout vira "Falhou" reenviável) → Alvo: **zero**; só o usuário reenvia um alvo "Incerto".

## Goals
- **Publicar não envia na requisição:** cria a publicação e os alvos `pending` e **redireciona imediatamente**; o envio é feito por um **worker** (processo separado).
- **Worker próprio no banco:** comando de gerenciamento (`run_worker`) em um segundo container, que reivindica alvos pendentes com o **claim atômico** existente (ADR-0004), sem Redis nem Celery, usando o mesmo SQLite e o mesmo volume de mídia.
- **Estado "Incerto"** (`uncertain`): quando a Evolution/Meta pode ter publicado mas o Hub não sabe (timeout depois de enviar; alvo `sending` cujo worker caiu e o *lease* expirou), o alvo **não é reenviado sozinho**. O usuário escolhe **"Já foi publicado"** (marca `published`, sem link) ou **"Reenviar"** (assume o risco de duplicar).
- **Recuperação sem duplicar (issue #1):** alvo `sending` com *lease* vencido vira `uncertain`, e não volta para `pending`.
- **Progresso na tela:** a página da publicação atualiza sozinha (*polling*) enquanto houver alvo `pending` ou `sending`, e para quando tudo terminar.
- **Sem limite de tempo por requisição:** o worker usa o timeout **por chamada** de cada plataforma (Evolution 120 s, Threads com espera de imagem etc.); o botão "Continuar envio" deixa de existir.
- **Operação visível:** a tela avisa quando **não há worker ativo** (alvos pendentes parados), e o worker registra um *heartbeat*.
- Preserva as invariantes existentes: `published` imutável, idempotência por claim, mensagens amigáveis, nenhum segredo em log.

## Non-goals
- **Agendamento** (a página Agenda): esta feature só **prepara o terreno**; a publicação com data/hora é a próxima feature.
- Celery/Redis/RabbitMQ, vários workers ou várias instâncias do Hub, e troca do SQLite por outro banco.
- Tempo real por SSE/WebSocket (basta *polling*).
- **Consultar a plataforma** para saber se um post já existe (cada API é diferente); fica como evolução futura do estado "Incerto".
- Retentativa automática com *backoff* para falhas conhecidas (recusa, reconexão necessária): continuam `failed` e reenviáveis pelo usuário.
- Cancelar um envio em andamento, prioridades e ordem global entre publicações.
- Mudar o contrato de qualquer plataforma (Graph, Threads, Evolution) ou as regras do formulário.

## Riscos / premissas
- **Premissa:** uma única instância do Hub e um único worker; o SQLite aguenta o worker e o Gunicorn escrevendo (usar *WAL* e *timeout* de lock).
- **Risco (operação):** se o worker não estiver rodando, nada é enviado. Mitigação: *heartbeat*, aviso na tela, healthcheck e README.
- **Risco (migração):** todos os testes e telas que assumem envio **síncrono** mudam; o caminho antigo (`send_pending` na requisição) precisa de um modo *inline* para testes e desenvolvimento simples (decisão no design).
- **Risco (UX do "Incerto"):** pedir uma decisão ao usuário pode incomodar; só vale para o caso de resultado realmente desconhecido (não para recusas conhecidas).
- **Risco:** *lease* curto demais marca como incerto um envio lento mas vivo (ex.: Status para milhares de contatos) → o *lease* é renovado enquanto o worker trabalha (*heartbeat* do alvo) e maior que o timeout da chamada.
- **Risco (concorrência no SQLite):** `database is locked` em picos; mitigação no design.
