---
name: product
description: PRD-lite da feature 0006 — publicar no Status do WhatsApp (texto e imagem) por uma instância da Evolution API já conectada, como mais um destino do formulário.
alwaysApply: false
---

# Product — WhatsApp: publicar no Status via Evolution API

> **Tier:** arquitetural · **Status:** rascunho · **Dono:** Thalyson
> Responde: **por quê** e **para quem**. Depende da [0003](../0003-publicar-no-facebook/spec.md) (publicação e imagens),
> da [0004](../0004-threads-conectar-e-publicar/spec.md) (plataforma como destino) e do [ADR-0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md) (despacho por plataforma).

## Problema
Quem publica pelo Hub escolhe Facebook e Threads num clique, mas o **Status do WhatsApp** — onde parte do público realmente vê o conteúdo —
precisa ser postado à mão, no celular, repetindo texto e imagem. O número já está conectado a uma **Evolution API** própria (Baileys), que
expõe o envio de Status por HTTP; falta o Hub usá-la como mais um destino.

## Para quem
O próprio operador do Hub, com um número de WhatsApp já pareado na sua Evolution. Uso recorrente, junto com as demais plataformas.

## Resultado esperado / métrica de sucesso
No formulário de publicação, além das Páginas e perfis existentes, aparece o **WhatsApp (Status)** como destino marcável; ao publicar,
o mesmo texto e imagem saem no Status do número, com resultado por destino no histórico.
- Métrica: passos manuais para publicar o mesmo conteúdo em Facebook, Threads e Status.
- Baseline: 3 postagens separadas (a do Status no celular) → Alvo: 1 envio pelo Hub.

## Goals
- **Cadastrar uma instância** da Evolution como conta do Hub (nome da instância + chave dela). A **URL base** vem do `.env`; a **chave** é
  guardada **cifrada**. Sem gerenciar QR: o número já está pareado na Evolution.
- **Marcar o WhatsApp no formulário** junto com Facebook e Threads; cada destino com seu resultado, falha reenviável e idempotência, como hoje.
- **Status de texto e de imagem.** A imagem (já sanitizada) vai **no corpo da requisição em base64**, sem URL pública nem túnel.
- **Audiência = todos os contatos** (a privacidade do número continua mandando).
- **Estado da conexão visível:** instância desconectada ou chave inválida marca a conta como "Reconexão necessária" e o alvo falha com mensagem clara.
- Segurança: URL da Evolution só do servidor (nunca informada pelo usuário), chave cifrada, nada sensível em logs/HTML/mensagens.

## Non-goals
- Pareamento por **QR code**, criação/exclusão de instâncias, ou qualquer gestão da Evolution além de ler o estado.
- Mensagens para **contatos, grupos ou canais**; só **Status**.
- Lista de contatos/JIDs escolhida no Hub (a audiência é "todos os contatos").
- Vídeo, áudio, figurinha, cor/fonte de fundo do Status de texto, enquete.
- Número oficial / **Cloud API** da Meta (aqui é Baileys); webhooks da Evolution; fila/worker; agendamento; apagar Status.
- Mudar o comportamento do Facebook ou do Threads.

## Riscos / premissas
- **Premissa:** a instância já está `open` (conectada) na Evolution e acessível por HTTPS a partir do Hub; a versão da Evolution expõe o envio de Status.
- **Risco (conta):** Baileys **não é oficial**; envio frequente pode levar a **banimento** do número. Mitigação: uso manual e esporádico, sem disparo em massa; documentar.
- **Risco (segurança):** a chave da instância envia mensagens pelo número → cifrar (Fernet), nunca logar, nunca usar a chave global da Evolution.
- **Risco (SSRF):** URL base fixa no servidor; o usuário informa só o nome da instância (validado).
- **Risco:** o contrato real do endpoint de Status (campos, tipos, resposta) varia por versão → confirmar na documentação **e** no UAT, sem inventar campos.
- **Risco:** Status não pode ser apagado pelo Hub (como os demais posts); testar com cuidado.
- **Risco:** imagem em base64 aumenta o corpo (~33%) e o tempo da requisição síncrona → respeitar o orçamento de tempo da [ADR-0009](../../docs/architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md).
