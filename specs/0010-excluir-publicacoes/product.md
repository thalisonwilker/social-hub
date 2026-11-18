---
name: product
description: PRD-lite da feature 0010 — excluir publicações (remover do Hub e apagar na plataforma onde a API permitir). Puxe ao abrir/rever a feature.
alwaysApply: false
---

# Product — Excluir publicações

> **Tier:** arquitetural · **Status:** aprovado · **Dono:** Thalyson
> Responde: **por quê** e **para quem**.

## Problema
Hoje uma publicação feita pelo Hub **não tem como ser removida**: nem o registro no histórico (e a imagem guardada no volume), nem o post nas redes. Posts de teste, errados ou duplicados (o UAT do WhatsApp e do Instagram já gerou alguns) exigem abrir cada rede e apagar à mão. O README registra explicitamente "o Hub não exclui posts".

## Para quem
O mesmo usuário do Hub, que publica em várias redes e precisa corrigir ou limpar publicações sem sair da tela de histórico.

## Resultado esperado / métrica de sucesso
- Métrica: de uma publicação publicada, o usuário apaga o post no Facebook e no Threads e remove o registro do Hub, em até 3 cliques e com confirmação.
- Baseline: 0 (não existe) → Alvo: UAT real apaga um post de teste no Facebook e no Threads.

## Goals
- **"Remover do Hub":** apagar a publicação (ou só um destino) do histórico, com a imagem do volume.
- **"Apagar na plataforma":** apagar o post publicado onde a API oficial permite (**Facebook** e **Threads**), por destino ou para a publicação inteira.
- Dizer com clareza, por destino, o que o Hub **não** consegue apagar (Instagram e WhatsApp) e mandar apagar pelo app.
- Confirmação obrigatória, só o dono, sem vazar segredos, e resultado desconhecido tratado sem mentir.

## Non-goals
- **Instagram:** a Meta anunciou uma API de exclusão em dez/2025, mas a documentação que li não traz endpoint, permissão nem limites; fica para uma versão futura, depois de confirmar no UAT.
- **WhatsApp (Status):** não há como apagar pelo Hub (Baileys/Evolution).
- Desfazer exclusão, lixeira, exclusão agendada, exclusão em massa de várias publicações marcadas na lista.
- Editar posts.

## Riscos / premissas
- Premissa (documentada): Facebook `DELETE /{post_id}` com token da Página; Threads `DELETE /{media_id}` com `threads_delete` (limite de 100/dia). **Se o Facebook só permite apagar posts criados pelo próprio app é incerto** (a doc só diz isso para editar) — validar no UAT.
- Risco: o `threads_delete` é uma permissão nova; contas do Threads já conectadas precisam **reconectar** e o app Meta precisa tê-la habilitada.
- Risco: exclusão é irreversível; mitigação: confirmação explícita e texto claro do que acontece.
