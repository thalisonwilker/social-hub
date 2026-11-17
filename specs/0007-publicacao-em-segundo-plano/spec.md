---
name: spec
description: Contrato da feature 0007 — publicar em segundo plano (worker no banco), estado Incerto com resolução manual, recuperação sem reenvio automático, progresso por polling e modo inline para dev/testes. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Publicação em segundo plano

> **Fonte da verdade.** Status: rascunho
> Os critérios de aceite são (a) o contrato com o negócio, (b) o oráculo de teste,
> (c) o prompt para o agente de IA implementar. Os `AC-N` desta spec são numerados a partir de 1 (independentes das anteriores).

## Resumo
Em produção, **Publicar** só enfileira (alvos `pending`) e responde na hora; um **worker** (`run_worker`, container próprio) envia fora da requisição, um alvo por vez. Quando o resultado de um envio é **desconhecido**, o alvo vira **Incerto** e **nunca** é reenviado sozinho: o usuário escolhe **Já foi publicado** ou **Reenviar**. A tela acompanha o progresso por polling. Em dev/testes o modo `inline` mantém o envio na requisição.

## Critérios de aceite
> Cada `AC-N` reaparece em `tasks.md` (coluna "Cobre AC"), no teste que o valida e no commit.

### AC-1: Publicar enfileira e responde na hora
- **Dado** `PUBLISH_MODE=worker` e um formulário válido com destinos de qualquer plataforma
- **Quando** o usuário publica
- **Então** a publicação e os alvos `pending` são criados, **nenhuma** plataforma é chamada durante a requisição, o usuário é redirecionado ao detalhe com a mensagem "Publicação enfileirada: o envio acontece em segundo plano", e os validadores/segurança do formulário (0003–0006) valem como antes

### AC-2: Modo inline
- **Dado** `PUBLISH_MODE=inline` (padrão em dev/testes)
- **Quando** o usuário publica, ou usa "Tentar novamente"
- **Então** o envio acontece **na requisição**, como na 0003–0006 (lote, orçamento de tempo e "Continuar envio" só neste modo), com as mesmas regras de classificação (`failed` × `uncertain`) do worker; `PUBLISH_MODE=worker` é o padrão em `config.settings.prod`

### AC-3: O worker envia um alvo por vez
- **Dado** alvos `pending` de uma ou mais publicações
- **Quando** o worker roda um ciclo
- **Então** ele reivindica o **mais antigo** (por id), o leva a `sending`, envia pelo despacho da sua plataforma e grava `published`/`failed`/`uncertain`; processa **um** alvo por vez; **não** usa orçamento por requisição (usa o timeout de cada chamada: Evolution `EVOLUTION_TIMEOUT_SECONDS`, Threads `THREADS_IMAGE_WAIT_SECONDS`, Graph como hoje); alvos de conta desconectada falham como hoje; o resultado por plataforma é o mesmo das 0003–0006

### AC-4: Reivindicação atômica
- **Dado** um alvo `pending` e dois processos tentando reivindicá-lo
- **Quando** ambos executam a reivindicação
- **Então** **exatamente um** o recebe (o outro recebe nada); alvo `sending`, `published`, `failed` ou `uncertain` **nunca** é reivindicado

### AC-5: Falha conhecida e "Tentar novamente"
- **Dado** um alvo `failed` (recusa, reconexão necessária, rede que nunca chegou ao servidor etc.)
- **Quando** o usuário usa "Tentar novamente" (modo `worker`)
- **Então** os alvos `failed` com conta voltam a `pending` (atômico, só quem estava `failed`), o usuário volta ao detalhe com "Reenvio enfileirado", `published` e `uncertain` **não** são tocados e **nada** é enviado na requisição

### AC-6: Resultado incerto
- **Dado** a **chamada com efeito** de um alvo (matriz de incerteza)
- **Quando** ela foi enviada e a resposta não chegou (tempo de leitura esgotado ou conexão cortada), ou a resposta foi inválida **depois** de o servidor aceitar
- **Então** o alvo vira `uncertain` com `error_code` (`timeout` ou `interrupted`) e a mensagem "Não foi possível confirmar se foi publicado. Confira na plataforma e escolha “Já foi publicado” ou “Reenviar”." (a conta **não** muda de status, o alvo **não** é reenviado sozinho e o log traz só `target_uncertain reason=…`); falhas **antes** de a requisição chegar ao servidor, respostas de erro da plataforma e falhas das chamadas preparatórias continuam `failed`

### AC-7: Recuperação na partida do worker
- **Dado** alvos `sending` quando o worker inicia (a execução anterior caiu ou foi encerrada à força)
- **Quando** o worker começa
- **Então** todos esses alvos viram `uncertain` com `error_code=worker_restart`, **nenhum** é reenviado, e é logado `worker_recovered n=<quantos>`

### AC-8: Alvo `sending` vencido
- **Dado** um alvo `sending` há mais de `PUBLISH_SENDING_STALE_SECONDS` (900)
- **Quando** o worker roda o ciclo seguinte
- **Então** o alvo vira `uncertain` com `error_code=stale` (sem reenviar); a recuperação automática de 5 min das 0003–0006 **deixa de existir**

### AC-9: Resolver "Já foi publicado"
- **Dado** um alvo `uncertain` de uma publicação do usuário
- **Quando** ele escolhe **Já foi publicado** e confirma
- **Então** o alvo vira `published` (sem link e sem id externo, mostrando "link indisponível"), mensagem de erro limpa, `published_at` agora; funciona **mesmo sem conta** (conta desconectada); qualquer outro estado de alvo é recusado e nada muda

### AC-10: Resolver "Reenviar"
- **Dado** um alvo `uncertain` com conta
- **Quando** o usuário escolhe **Reenviar** e confirma (aviso de que pode duplicar o post)
- **Então** o alvo volta a `pending` (atômico) e o worker o envia; alvo **sem conta** não pode ser reenviado (mensagem clara); estados diferentes de `uncertain` são recusados

### AC-11: Status geral com Incerta
- **Dado** uma publicação com alvos em estados variados
- **Quando** o status geral é calculado (detalhe, histórico)
- **Então** vale a precedência `failed` > `uncertain` > `published` (todos) > `pending`; o rótulo geral para incerteza é **"Incerta"**; o detalhe e o histórico mostram as contagens por estado inclusive "N incerto(s)"

### AC-12: Estado para polling
- **Dado** o dono de uma publicação
- **Quando** consulta `GET /publicacoes/<id>/estado/`
- **Então** recebe JSON com `status` geral, `counts`, `targets` (`id`, `status`), `worker.active` e `done` (`true` quando nenhum alvo está `pending`/`sending`), **sem** texto, tokens, nomes de conta, mensagens de erro nem URLs; outro usuário recebe 404; só `GET`

### AC-13: A tela acompanha sozinha
- **Dado** o detalhe de uma publicação com alvo `pending` ou `sending`
- **Quando** a página está aberta
- **Então** ela consulta o estado a cada ~3 s, **recarrega** quando o conjunto de estados dos alvos muda e **para** de consultar quando `done=true`; com tudo já terminado, nenhuma consulta é feita; os alvos `pending` aparecem como "Na fila" e `sending` como "Enviando…"

### AC-14: Aviso de worker inativo
- **Dado** `PUBLISH_MODE=worker`, alvos `pending`/`sending` e o *heartbeat* ausente ou mais antigo que `WORKER_HEARTBEAT_STALE_SECONDS` (180)
- **Quando** o usuário abre o detalhe
- **Então** aparece o aviso "O envio em segundo plano não está ativo: os envios ficam na fila até o worker voltar"; com *heartbeat* recente, ou sem alvos em andamento, ou em modo `inline`, o aviso **não** aparece

### AC-15: Comando `run_worker`
- **Dado** o comando `python manage.py run_worker`
- **Quando** roda
- **Então** grava o *heartbeat* (`started_at`, `beat_at`, `pid`) a cada ciclo e entre alvos, dorme `WORKER_POLL_SECONDS` (2) sem fila, **termina o alvo atual e sai** ao receber SIGTERM/SIGINT, e `--once` executa um único ciclo (para testes e manutenção); `python manage.py worker_health` sai com código **0** se o *heartbeat* é recente e **1** caso contrário

### AC-16: Compose com o serviço `worker`
- **Dado** o `docker-compose.yml`
- **Quando** inspecionado
- **Então** existe o serviço `worker` com a **mesma imagem**, `command` `python manage.py run_worker`, `RUN_MIGRATIONS=0`, `depends_on` o `web` saudável, os **mesmos volumes** (`sqlite_data`, `media_data`), `restart: unless-stopped`, `stop_grace_period` ≥ 150 s e *healthcheck* com `worker_health`

### AC-17: Isolamento e segurança
- **Dado** qualquer fluxo desta feature
- **Quando** usado por outro usuário, sem login, por GET onde exige POST ou sem CSRF
- **Então** estado, resolver e "Tentar novamente" operam **só** nas publicações do próprio usuário (404 nas dos outros), exigem POST com CSRF e login, e **nenhum** log/JSON/HTML novo traz chave, token, texto da publicação, base64 ou o corpo cru da plataforma

### AC-18: Migração aditiva e reversão
- **Dado** o banco das 0003–0006
- **Quando** a migração desta feature roda
- **Então** só **adiciona** (estado `uncertain`, `WorkerHeartbeat`), mantendo todos os dados; alvos `pending` existentes passam a ser enviados pelo worker; trocar `PUBLISH_MODE` para `inline` volta ao envio na requisição **sem** nova migração

### AC-19: Documentação e ADR
- **Dado** o repositório
- **Quando** consultado
- **Então** o README explica o worker (`run_worker`, `worker_health`, compose, modos, o que fazer com "Incerto"), `.env.example` traz `PUBLISH_MODE` e as quatro settings novas, e o **ADR-0011** registra a decisão (worker no banco, `uncertain`, recuperação sem reenvio, substituição parcial dos ADRs 0004 e 0009)

### AC-20: Compatibilidade com as specs anteriores
- **Dado** as specs 0003, 0004, 0005 e 0006
- **Quando** consultadas
- **Então** registram as notas de supersessão desta feature (envio em segundo plano; "Continuar envio", a recuperação de 5 min e o orçamento por requisição valem só no modo `inline`; a mensagem de timeout do WhatsApp passa a ser o estado **Incerto**), e a suíte das 0002–0006 continua verde em modo `inline`

## Matriz de decisão

### Incerteza por plataforma (AC-6)
| Plataforma | Chamada | Situação | Resultado | `error_code` |
|---|---|---|---|---|
| Facebook | `POST /{page}/photos` (efeito) | tempo de leitura esgotado | `uncertain` | `timeout` |
| Facebook | idem | conexão cortada depois de enviar | `uncertain` | `interrupted` |
| Facebook | idem | DNS/recusada/TLS (nunca chegou) | `failed` | `network` |
| Facebook | idem | resposta de erro da Meta (token, permissão, limite…) | `failed` | como hoje |
| Threads | `POST /{user}/threads_publish` (efeito) | tempo de leitura / conexão cortada | `uncertain` | `timeout` / `interrupted` |
| Threads | criação do container, consulta de status, espera esgotada | qualquer falha | `failed` (container mantido, como na 0005) | como hoje |
| Threads | `threads_publish` | nunca chegou / erro da Meta | `failed` | como hoje |
| WhatsApp | `POST /message/sendStatus` (efeito) | tempo de leitura esgotado | `uncertain` | `timeout` |
| WhatsApp | idem | conexão cortada depois de enviar | `uncertain` | `interrupted` |
| WhatsApp | idem | DNS/recusada/TLS (nunca chegou) | `failed` | `network` |
| WhatsApp | idem | 4xx/5xx com resposta; instância fora; chave recusada | `failed` | como hoje (0006) |
| WhatsApp | `connectionState` (cadastro/sonda) | qualquer falha | sem efeito sobre o alvo | — |
| Qualquer | — | worker reiniciado com o alvo `sending` | `uncertain` | `worker_restart` |
| Qualquer | — | `sending` além de `PUBLISH_SENDING_STALE_SECONDS` | `uncertain` | `stale` |

### Ações do usuário × estado do alvo (AC-5, AC-9, AC-10)
| Estado do alvo | Ação | Resultado |
|---|---|---|
| `failed` (com conta) | Tentar novamente | → `pending` |
| `failed` (sem conta) | Tentar novamente | ignorado (não reenviável) |
| `pending` | Tentar novamente | ignorado (já está na fila) |
| `sending` | qualquer | recusado, nada muda |
| `published` | qualquer | recusado, nada muda |
| `uncertain` | Tentar novamente | **ignorado** (precisa Resolver) |
| `uncertain` | Já foi publicado | → `published` (sem link; sem exigir conta) |
| `uncertain` (com conta) | Reenviar | → `pending` |
| `uncertain` (sem conta) | Reenviar | recusado com mensagem |
| qualquer | ação de outro usuário | 404 |

### Modo de publicação (AC-1, AC-2, AC-14, AC-18)
| `PUBLISH_MODE` | Publicar / Tentar novamente | Aviso de worker | "Continuar envio" |
|---|---|---|---|
| `worker` | só enfileira | sim, se inativo e há alvos em andamento | não existe |
| `inline` | envia na requisição (lote + orçamento) | nunca | existe (só neste modo) |

## Casos de borda e erros
- **Worker parado:** os alvos ficam `pending`; o aviso aparece (AC-14); ao voltar, o worker retoma pela ordem de criação.
- **Duplo clique** em "Reenviar"/"Tentar novamente": a transição é condicional (`UPDATE … WHERE status=…`); só a primeira vale.
- **Conta desconectada com alvo `pending`:** o worker o marca `failed` como hoje ("Conta desconectada"), sem chamar a plataforma.
- **Imagem ausente do disco:** `failed` como hoje, sem chamar a plataforma.
- **`database is locked`:** o worker repete no ciclo seguinte; nenhuma transição é perdida (as transições são atômicas).
- **Exceção inesperada no worker** (bug) depois da reivindicação: o alvo vira Incerto (`error_code=worker_error`) — não se sabe se a plataforma chegou a publicar — e o worker **continua**; o log traz só o tipo da exceção, nunca a mensagem.
- **SIGKILL no meio do envio:** na partida seguinte o alvo vira `uncertain` (AC-7); o usuário decide.
- **Fila grande/envio lento:** um Status lento atrasa os seguintes (um worker, sequencial) — aceito.
- **Publicação mista com um alvo incerto:** os outros alvos seguem normalmente; o geral fica "Com falhas" se houver `failed`, senão "Incerta".
- **`PUBLISH_MODE=inline` em produção por engano:** o comportamento volta ao antigo, sem perda de dados (AC-18).

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Agendamento e a tela Agenda; vários workers/instâncias; Celery/Redis; SSE/WebSocket.
- Consultar a plataforma para resolver o Incerto sozinho; retentativa automática com *backoff*.
- Cancelar envio em andamento, prioridades, ordem global configurável.
- Mudar contratos das plataformas, regras do formulário ou o que cada plataforma publica.

## Rastreabilidade
- Product: [`./product.md`](./product.md)
- Design: [`./design.md`](./design.md)
- Domínio: [`./domain.md`](./domain.md)
- ADRs relacionados: [0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md) · [0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md) · [0009](../../docs/architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md) · [0011](../../docs/architecture/adr/0011-publicacao-em-segundo-plano-worker-no-banco-estado-incerto-e-recuperacao-sem-reenvio.md) (worker no banco, `uncertain`, recuperação sem reenvio)
- Specs afetadas: [0003](../0003-publicar-no-facebook/spec.md) (envio em lote, recuperação de `sending`), [0004](../0004-threads-conectar-e-publicar/spec.md) e [0005](../0005-threads-imagem/spec.md) (orçamento/continuar envio), [0006](../0006-whatsapp-status/spec.md) (mensagem de timeout → Incerto).
- Issues: [#1](https://github.com/thalisonwilker/social-hub/issues/1) (duplicidade) e [#4](https://github.com/thalisonwilker/social-hub/issues/4) (fila/worker).
