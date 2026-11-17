---
name: ADR-0006
description: Threads com cliente e OAuth próprios; token de 60 dias guardado com expiração e renovado sob demanda.
alwaysApply: false
---

# ADR-0006: Threads — cliente próprio, token de 60 dias com renovação sob demanda

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A feature `0004-threads-conectar-e-publicar` integra o Threads. Diferentemente do Facebook (ADR-0003), o Threads tem **login em
`threads.com`, API em `graph.threads.com`, credenciais próprias** (`THREADS_APP_ID/SECRET`) e **tokens que expiram em 60 dias**
(token curto de 1 h → longo de 60 dias; renovável após 24 h de vida). O redirect do OAuth exige **HTTPS**. O projeto não tem
fila/worker. A Meta documenta alguns GETs (troca, renovação, perfil, status, permalink) com o token na **query string**.

## Decisão
- Criamos um **`ThreadsClient` próprio** (camada anticorrupção), irmão do `GraphClient`, sobre uma **base comum** de requisição
  sanitizada (host, versão, timeout, erros). Não misturamos os dois protocolos no mesmo cliente.
- O token de longa duração é guardado **criptografado** (ADR-0002) junto com **`token_expires_at`** e **`token_refreshed_at`**.
- **Renovação sob demanda:** ao publicar e ao Verificar, se faltarem **< 30 dias** e o token tiver **≥ 24 h**, chamamos
  `th_refresh_token`; token já expirado → `needs_reauth`. *Contas conectadas* só sinaliza a validade (cálculo local).
- **Segredos:** `client_secret` e `code` vão em **POST**; onde a Meta documenta **GET com token na URL**, mantemos as salvaguardas
  (URLs, parâmetros e corpos **nunca** logados nem exibidos; exceções sanitizadas) e **testamos POST/Bearer** no UAT para adotar se aceitos.
- A conexão deve ser iniciada pelo **mesmo host** do `THREADS_REDIRECT_URI` (cookie de sessão por host); o Hub avisa quando não for.
- Alternativas descartadas: **renovar em segundo plano** (exige fila/cron; fica para quando houver agendamento), **reusar o `GraphClient`
  com flags** (mistura protocolos) e **ignorar a expiração** (contas quebrariam sem aviso).

## Consequências
- **+** Isolamento do protocolo do Threads; token com expiração modelado de forma explícita e reutilizável por outras plataformas.
- **+** Sem worker; a renovação acontece quando o usuário usa o sistema.
- **−** Token sem uso por mais de 60 dias expira e exige reconexão.
- **−** Tokens na query dos GETs documentados dependem de **não registrar URLs** (disciplina + testes).
- **−** Em desenvolvimento, a URL do túnel HTTPS muda e exige atualizar a Meta e o `.env`; em produção, exige domínio com TLS.
