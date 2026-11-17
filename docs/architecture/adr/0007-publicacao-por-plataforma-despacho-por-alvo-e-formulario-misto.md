---
name: ADR-0007
description: Publicação por plataforma com despacho por alvo e formulário de destinos mistos (imagem condicional).
alwaysApply: false
---

# ADR-0007: Publicação por plataforma — despacho por alvo e formulário misto

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A 0003 publica texto + imagem em Páginas do Facebook, com claim atômico por alvo, lotes de 5, retry e histórico (ADR-0004).
A 0004 acrescenta o Threads, que só publica **texto** (≤ 500, emoji por bytes UTF-8, ≤ 5 links) e exige **container → espera → publicar**.
O produto quer **publicar uma vez e escolher os destinos**, inclusive misturando plataformas, e ainda virão Instagram e outros.

## Decisão
- O envio de cada alvo **despacha por `account.platform`**: `facebook_page` → fluxo atual; `threads` → `ThreadsPublisher`.
  **Claim atômico, lote, retry, `needs_reauth` e mapeamento de erros permanecem comuns** (ADR-0004 continua valendo).
- O **formulário é único e misto**: lista Páginas do Facebook e perfis do Threads ativos.
  - **Imagem obrigatória apenas se houver Página do Facebook marcada**; só-Threads → imagem opcional e **ignorada** (não gravada).
  - **Limites por destino:** texto até 5000; se houver Threads marcado, até 500 de "peso" (emoji = 4) e no máximo 5 links únicos.
  - A validação da imagem passa a ocorrer em `Form.clean()`, pois depende dos destinos.
- `Publication.image` torna-se **opcional**; o alvo do Threads guarda o `external_container_id` para **retomar** sem recriar o container.
- Alternativas descartadas: **fluxo/serviço separado para o Threads** (duplicaria claim/lote/retry e impediria alvo misto) e
  **plataformas em publicações distintas** (o usuário repetiria o texto).

## Consequências
- **+** Um único fluxo e histórico para todas as plataformas; adicionar Instagram vira um novo publicador.
- **+** Reuso integral das garantias de idempotência da 0003.
- **−** Refatoração do `_publish_target` e da validação do formulário; risco de regressão na 0003, coberto pela suíte existente.
- **−** No Threads o conteúdo difere do Facebook (sem imagem), o que exige avisos claros na tela.
- **−** A regra "imagem obrigatória" da 0003 muda; os critérios afetados serão atualizados na spec 0003.
