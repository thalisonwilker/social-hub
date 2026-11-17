---
name: ADR-0010
description: WhatsApp (Status) via Evolution API — conta = instância com chave cifrada, host só do servidor, imagem em base64 e o risco de usar Baileys (não oficial).
alwaysApply: false
---

# ADR-0010: WhatsApp (Status) via Evolution API — instância com chave cifrada e host fixo

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A feature `0006-whatsapp-status` publica o **Status do WhatsApp** a partir do formulário do Hub, usando uma **Evolution API do próprio operador**,
com um número já pareado por **Baileys** (WhatsApp Web, **não oficial**). Diferente de Facebook e Threads, não há OAuth, não há conexão interativa
(o pareamento por QR é feito na Evolution) e o envio é uma chamada única. A chave da instância permite **enviar mensagens pelo número**, e a Evolution
também tem uma chave global com poder total. O host da Evolution é de um sistema de terceiros (do operador) e, se viesse do usuário, abriria **SSRF**.
A documentação oficial do endpoint de Status não pôde ser lida na construção desta feature: o corpo exato é isolado no cliente e fixado no UAT.

## Decisão
- **Conta = instância.** Nova plataforma `whatsapp_status` reaproveita `SocialAccount`: `external_id` = nome da instância (`^[A-Za-z0-9_-]{1,64}$`),
  `access_token_enc` = **chave da instância**, cifrada com Fernet (ADR-0002). Sem tabela nova; o despacho por alvo é o do ADR-0007.
- **Host só do servidor.** `EVOLUTION_API_URL` (HTTPS; só a origem é usada, caminho/query descartados; usuário/senha embutidos recusados). O usuário informa apenas
  o nome da instância, validado no formulário **e** no cliente antes de qualquer chamada. Evita SSRF e injeção de caminho.
- **Chave por instância, nunca a global.** O Hub só conhece a chave da instância; a chave global da Evolution não é pedida nem usada.
- **Imagem em base64**, no corpo da chamada, a partir do arquivo já sanitizado (ADR-0005): sem URL pública, sem túnel, sem a rota pública do ADR-0008.
- **Audiência = todos os contatos** (a privacidade do número manda); sem lista de JIDs no Hub.
- **Uma chamada, sem retomada.** Sem container/espera; falha → alvo `failed` reenviável. Timeout = `min(EVOLUTION_TIMEOUT_SECONDS, orçamento restante − 25 s)` (ADR-0009).
- **Estado da conexão:** o cadastro exige `open`; 401/403/404 ou instância fora de `open` marcam a conta como Reconexão necessária (o pareamento é refeito na Evolution).
  Depois de uma falha ambígua (recusa, 5xx, resposta inválida) o Hub sonda o estado (≤ 10 s) para distinguir "instância caiu" de "conteúdo recusado".
- **Sem segredos em log/HTML/mensagens:** só rótulo do endpoint, status HTTP e código curto; o corpo cru da Evolution nunca sobe.
- **Alternativas descartadas:** URL e chave globais no `.env` (uma instância só e poder total); URL pública assinada para a imagem (exige túnel/domínio e expõe a imagem);
  modelo `EvolutionInstance` separado (novo agregado sem ganho); WhatsApp Cloud API oficial (outro produto, com templates e janela de 24 h).

## Consequências
- **+** Mais um destino sem OAuth, sem infra nova e sem rota pública; segredo cifrado e superfície de rede mínima.
- **+** Reaproveita idempotência, orçamento, histórico e reconexão já existentes.
- **−** **Baileys não é oficial**: envio frequente pode levar ao **banimento do número**; o uso deve ser manual e esporádico (documentado no README e no `.env.example`).
- **−** O contrato do Status (corpo, base64, resposta, estado) varia por versão e é fixado no UAT; até lá é hipótese isolada em `EvolutionClient`.
- **−** Sem idempotência forte: timeout depois de a Evolution já ter enviado pode duplicar o Status num reenvio (mesma janela da issue #1).
- **−** `external_id`/token com semântica por plataforma (documentada no glossário).
