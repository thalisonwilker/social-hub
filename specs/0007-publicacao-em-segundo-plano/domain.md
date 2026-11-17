---
name: domain
description: Modelo DDD da feature 0007 — fila de envio no banco, worker, alvo Incerto, resolução manual e heartbeat; máquina de estados do alvo.
alwaysApply: false
---

# Domain Model (DDD) — Publicação em segundo plano

> Evolui `Publication`/`PublicationTarget` (0003–0006) no contexto **Social (integrações)**, subdomínio **core**.

## Bounded Context
**Social (integrações)** (`apps.social`). Nenhum contexto novo: o **worker** é um **processo** do mesmo contexto (mesmo código, mesmo banco), não um serviço separado.

## Linguagem ubíqua

| Termo                 | Definição                                                                                                  | NÃO confundir com                         |
|-----------------------|------------------------------------------------------------------------------------------------------------|-------------------------------------------|
| Fila de envio         | O conjunto dos alvos `pending`, em ordem de criação (FIFO). Não é uma tabela à parte.                       | Lote (limite de quantidade da 0003)       |
| Worker                | Processo `run_worker` que reivindica um alvo `pending` por vez e o envia.                                   | Worker do Gunicorn (atende HTTP)          |
| Enfileirar            | Criar/Reenviar um alvo como `pending` sem falar com a plataforma.                                           | Enviar                                    |
| Alvo Incerto          | Alvo (`uncertain`) cujo envio **pode** ter sido concluído pela plataforma, mas o Hub não sabe.              | Alvo Falhou (sabe-se que nada foi publicado) |
| Resolver              | Decisão do usuário sobre um alvo Incerto: **Já foi publicado** (vira `published`) ou **Reenviar** (volta a `pending`). | Tentar novamente (só para `failed`) |
| Chamada com efeito    | A chamada à plataforma que cria o post (upload do Facebook, `threads_publish`, `sendStatus`).               | Chamadas preparatórias (container, estado) |
| Heartbeat do worker   | Registro (`WorkerHeartbeat`) atualizado pelo worker; diz se há worker ativo.                                | Healthcheck do Gunicorn (`/healthz/`)     |
| Modo de publicação    | `PUBLISH_MODE`: `worker` (envia fora da requisição) ou `inline` (na requisição, dev/testes).                | Plataforma                                |

## Agregados, entidades e value objects
- **Agregado `Publication`** (raiz: `Publication`; entidade: `PublicationTarget`) — evolução da 0003–0006.
  - Novo estado do alvo: `uncertain` ("Incerto"). Códigos de motivo (`error_code`): `timeout`, `interrupted`, `worker_restart`, `stale`.
  - **Máquina de estados do alvo (invariantes):**
    1. `pending → sending` **só** por reivindicação atômica; **no máximo um** processo tem o alvo.
    2. `sending → published | failed | uncertain`; **nunca** `sending → pending` automaticamente (fim da recuperação automática, issue #1).
    3. `failed → pending` só por "Tentar novamente" do usuário.
    4. `uncertain → pending` só por **Reenviar** (decisão do usuário) e **exige conta ativa**; `uncertain → published` só por **Já foi publicado** (não exige conta).
    5. `published` é imutável; "Já foi publicado" grava `published` com `permalink` vazio e `external_post_id` vazio (link indisponível).
    6. Enfileirar **não** chama plataformas.
  - **Resultado incerto** se, e somente se, a **chamada com efeito** foi enviada e a resposta não chegou (tempo de leitura, conexão cortada), ou o worker morreu/reiniciou com o alvo `sending`, ou `sending` passou de `PUBLISH_SENDING_STALE_SECONDS`. Falha **antes** de a requisição chegar ao servidor (DNS, conexão recusada, TLS) e recusas da plataforma são `failed`.
  - **Status geral derivado:** `failed` > `uncertain` > `published` (todos) > `pending`; rótulo novo **"Incerta"**.
  - Fronteira de consistência: cada transição é um `UPDATE` condicional (compare-and-set) sobre **um** alvo; a publicação não é lida/escrita em bloco.
- **Entidade `WorkerHeartbeat`** (fora do agregado): linha única (`name="default"`) com `started_at`, `beat_at`, `pid`. **Ativo** ⇔ `beat_at` mais recente que `WORKER_HEARTBEAT_STALE_SECONDS`.
- **Invariantes do worker:** processa **um** alvo por vez, em ordem de criação; **na partida**, todo alvo `sending` vira `uncertain` (`worker_restart`); ao receber SIGTERM termina o alvo atual e sai.
- **Acesso:** o estado, o resolver e o enfileirar só funcionam para o **dono** da publicação (404 caso contrário).

## Eventos de domínio
> Eventos **lógicos** em log (`apps.social.meta`); sem barramento. **Nenhum log traz chave, texto ou conteúdo.**

| Evento (passado)               | Disparado quando                                              | Quem reage                          |
|--------------------------------|---------------------------------------------------------------|-------------------------------------|
| `PublicacaoEnfileirada`        | Publicar cria os alvos `pending` (modo `worker`)              | tela (redireciona), log             |
| `AlvoReenfileirado`            | "Tentar novamente" ou "Reenviar"                              | worker, log                         |
| `AlvoReivindicado`             | O worker leva um alvo de `pending` para `sending`             | log (`worker_target_claimed`)       |
| `AlvoPublicado` / `AlvoFalhou` | Resultado conhecido (já existentes)                           | histórico, log                      |
| `AlvoFicouIncerto`             | Efeito sem resposta, reinício do worker ou `sending` vencido  | tela (botões Resolver), log (`target_uncertain reason=…`) |
| `IncertoResolvido`             | Usuário escolhe "Já foi publicado" ou "Reenviar"              | histórico, log                      |
| `WorkerIniciou` / `WorkerRecuperouAlvos` | Partida do worker (e quantos `sending` foram para incerto) | log                          |
| `WorkerInativoDetectado`       | A tela vê alvos `pending/sending` e heartbeat vencido         | aviso na tela                       |

## Relações com outros contextos
- **Plataformas (Graph, Threads, Evolution) → Social:** as **ACLs** (`GraphClient`, `ThreadsClient`, `EvolutionClient`) passam a **classificar** o erro em "nunca chegou ao servidor" (`network`) × "enviei e não veio resposta" (`interrupted`/`timeout`), para o Social decidir `failed` × `uncertain`.
- **Usuário (navegador) → Social:** a tela consulta o estado por **polling** (`GET …/estado/`); sem canal persistente.
- **Social → Identidade, Painel:** sem mudança.
