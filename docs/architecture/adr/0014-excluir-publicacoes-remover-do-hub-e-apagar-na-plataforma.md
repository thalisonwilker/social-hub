---
name: ADR-0014
description: Exclusão de publicações — duas ações separadas (Remover do Hub e Apagar na plataforma), deleted_at no alvo, Facebook e Threads, resposta desconhecida nunca marca apagado.
alwaysApply: false
---

# ADR-0014: Excluir publicações — Remover do Hub e Apagar na plataforma

- **Status:** aceito
- **Data:** 2026-11-18
- **Decisores:** Thalyson

## Contexto
O Hub não tinha como apagar uma publicação nem o post nas redes. A Meta documenta `DELETE /{page_post_id}` (Página, token da Página) e, no Threads, `DELETE /{media_id}` com a permissão `threads_delete` (100/dia). Para o Instagram, a Meta anunciou (dez/2025) uma API de exclusão, mas a documentação consultada não traz endpoint, permissão nem limites; o WhatsApp Status (Baileys/Evolution) não é apagável pelo Hub.

## Decisão
- **Duas ações separadas:** *Remover do Hub* (apaga alvo/publicação e a imagem do volume) e *Apagar na plataforma* (chama a API). Uma não implica a outra, para não perder o rastro (id do post) quando a plataforma falha.
- **`PublicationTarget.deleted_at`** em vez de um novo status: o alvo continua `published` (contagens, polling e status geral inalterados); a tela mostra "Apagado na plataforma".
- **Só Facebook e Threads.** Instagram e WhatsApp: sem botão, "Apague pelo app" (Instagram adiado até a documentação estar clara/validada no UAT).
- **Síncrono na requisição** (chamada curta). Sucesso ou "objeto inexistente" → `deleted_at` (atômico). **Resposta desconhecida nunca grava** `deleted_at`; repetir é idempotente.
- **Bloqueio:** não remove publicação com alvo `sending`.
- Escopo `threads_delete` entra no login do Threads; contas antigas reconectam.
- Descartado: uma ação única "apagar tudo" (perde o id se a plataforma falhar), status `deleted` (espalha o estado) e exclusão assíncrona no worker (desnecessária).

## Consequências
- **+** Limpar testes/erros sem abrir cada rede; histórico preservado até o usuário remover.
- **+** Nenhuma mudança no fluxo de envio nem nas contagens.
- **−** Threads exige reconexão e a permissão no app Meta.
- **−** Comportamentos não documentados (Facebook com posts criados fora do app, códigos de "inexistente") ficam para o UAT.
