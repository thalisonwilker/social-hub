---
name: product
description: PRD-lite da feature 0009 — publicar imagem + legenda no Instagram (conta profissional vinculada a uma Página já conectada). Puxe ao abrir/rever a feature.
alwaysApply: false
---

# Product — Instagram: conectar pela Página e publicar

> **Tier:** arquitetural · **Status:** aprovado · **Dono:** Thalyson
> Responde: **por quê** e **para quem**.

## Problema
O Hub publica no Facebook, Threads e WhatsApp (Status), mas o Instagram — a rede mais visual e a que o usuário mais quer atingir com a mesma imagem — ainda exige abrir o app e repetir o post à mão. O produto prometia "Facebook, Instagram e Threads" e o Instagram foi adiado em todas as specs anteriores (0002–0005, "Fora de escopo").

## Para quem
O mesmo usuário do Hub: quem administra Páginas e perfis e quer **publicar uma vez e escolher os destinos**. Aqui, o dono de uma **conta profissional do Instagram** (Business ou Creator) **vinculada a uma Página do Facebook** que ele administra e já conectou ao Hub.

## Resultado esperado / métrica de sucesso
- Métrica: uma publicação com imagem e destino Instagram marcado chega **publicada** no Instagram (com link), sem sair do Hub.
- Baseline: hoje 0 publicações no Instagram pelo Hub → Alvo: o UAT real publica 1 imagem + legenda numa conta de teste e o link abre o post.

## Goals
- Conectar o Instagram **a partir da Página** já conectada (mesmo login da Meta, sem segundo OAuth).
- Publicar **imagem + legenda** como destino do formulário misto, pelo worker, com o mesmo estado por alvo (Pendente → Enviando → Publicado/Falhou/Incerto) e os mesmos "Tentar novamente"/"Já foi publicado"/"Reenviar".
- Validar **antes** de criar a publicação o que o Instagram recusa (imagem obrigatória, proporção, legenda, endereço público), com mensagens claras.
- Nunca duplicar post: resultado desconhecido na publicação vira **Incerto**.

## Non-goals
- Instagram **sem Página** (API com Instagram Login / login unificado, token próprio) — registrado como alternativa futura no design.
- Reels, Stories, carrossel, vídeo, marcar pessoas/produtos, `alt_text`, local, comentários, DMs e insights.
- Agendamento, App Review / modo Live, e vários usuários da Meta além dos que têm função no app.
- Cortar/reenquadrar a imagem automaticamente; truncar a legenda.

## Riscos / premissas
- Premissa: a conta é profissional e está vinculada à Página; o app Meta tem o caso de uso do Instagram e o `config_id` inclui `instagram_basic` e `instagram_content_publish` (validado com o usuário; **a ser confirmado no UAT**).
- Risco: o buscador do Instagram precisa alcançar a URL pública do Hub (túnel em dev, HTTPS) — mesma dependência do Threads (ADR-0008).
- Risco: comportamento da Graph API do Instagram (campos, limites, códigos de erro) vem do conhecimento da documentação, **não** confirmado no código — validar no UAT.
- Risco: limite de ~100 publicações por 24 h por conta; tratado como erro amigável.
