---
name: ADR-0013
description: Instagram publicado pela Graph API com login do Facebook — Conta Instagram vinculada à Página, token da Página, container e imagem JPEG em URL pública própria.
alwaysApply: false
---

# ADR-0013: Instagram via Página — conta vinculada, token da Página e imagem JPEG pública

- **Status:** aceito
- **Data:** 2026-11-18
- **Decisores:** Thalyson

## Contexto
A feature `0009-instagram-publicar` publica imagem + legenda no Instagram. O app Meta usa o Login do Facebook for Business (`config_id`, ADR-0003) e já conecta Páginas. A Graph API do Instagram com login do Facebook alcança a conta profissional **pela Página vinculada**, com o **token da Página**, em dois passos (container → publicar), e o Instagram **baixa a imagem de uma URL pública** em **JPEG** (como o Threads, ADR-0008). O painel da Meta marca essa configuração como **obsoleta**, recomendando o login unificado (comportamento ainda não confirmado).

## Decisão
- **Conta Instagram** = `SocialAccount` com `platform=instagram`, `parent` (FK para a Página, `CASCADE`) e o **mesmo token cifrado** da Página (ADR-0002). Criada/atualizada/removida **automaticamente** ao salvar a Página, conforme `instagram_business_account` (um único `GET /me/accounts` com o campo extra).
- **Publicador próprio** (`instagram_publish`), despachado por plataforma (ADR-0007), com container gravado antes da espera, `media_publish` como **chamada com efeito** (sem resposta → **Incerto**, ADR-0011).
- **Rota pública própria** `/publico/instagram.jpg`, com o mesmo token assinado do ADR-0008 mas **escopo próprio**: só serve com alvo **Instagram** em andamento (e a rota do Threads só com alvo Threads). PNG é **convertido para JPEG só nessa entrega** (transparência sobre branco); a imagem armazenada e as do Facebook/Threads não mudam.
- Validações **no formulário** (imagem obrigatória, proporção 0,8–1,91, largura ≥ 320, legenda ≤ 2.200 e ≤ 30 hashtags): rejeitar, nunca cortar nem truncar.
- Alternativa **descartada por ora:** Instagram Login / login unificado (sem Página, OAuth e token próprios) — comportamento não confirmado; a troca fica isolada no cliente e na conexão. Também descartadas: converter PNG ao salvar (muda as outras plataformas) e cortar a imagem sozinho (altera o enquadramento sem avisar).

## Consequências
- **+** Instagram com um módulo novo, reaproveitando login, token cifrado, worker, estado Incerto e URL assinada.
- **+** Uma URL assinada de uma plataforma não abre a imagem de outra.
- **−** Depende de uma configuração que a Meta marca como obsoleta; se for descontinuada, troca-se a conexão/cliente (Instagram Login).
- **−** Mais uma rota anônima (escopo mínimo, 404 uniforme, sem token em log).
- **−** Campos, limites e códigos de erro vêm da documentação; confirmar no UAT.
