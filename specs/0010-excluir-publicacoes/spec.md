---
name: spec
description: Contrato da feature 0010 — excluir publicações: Remover do Hub e Apagar na plataforma (Facebook e Threads), por destino e por publicação. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Excluir publicações

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT real)
> Os `AC-N` desta spec são numerados a partir de 1.

## Resumo
Duas ações, sempre com confirmação e só para o dono: **Remover do Hub** (histórico e imagem) e **Apagar na plataforma** (Facebook e Threads), por destino ou para a publicação inteira. Instagram e WhatsApp ficam com o aviso "Apague pelo app".

## Critérios de aceite

### AC-1: Remover a publicação do Hub
- **Dado** uma publicação do usuário sem alvo `sending`
- **Quando** ele confirma "Remover do Hub" (`POST`)
- **Então** a publicação e todos os seus alvos são apagados, o **arquivo da imagem** é removido do volume, é logado `publication_removed` (sem texto nem ids externos) e o usuário volta à lista com mensagem de sucesso; nenhuma plataforma é chamada

### AC-2: Publicação enviando não é removida
- **Dado** uma publicação com ao menos um alvo `sending`
- **Quando** o usuário tenta removê-la
- **Então** nada é apagado e a mensagem diz que o envio está em andamento; alvos `pending` (na fila) de uma publicação sem `sending` são removidos junto, o que cancela o envio

### AC-3: Remover um destino
- **Dado** um alvo que não está `sending`
- **Quando** o usuário confirma "Remover do Hub" naquele destino
- **Então** só esse alvo é apagado; se era o **último**, a publicação e a imagem também são removidas; os outros destinos e o status geral (derivado) continuam corretos

### AC-4: A confirmação diz o que acontece
- **Dado** uma ação de remover ou apagar
- **Quando** a tela a apresenta
- **Então** o botão tem confirmação do navegador; a de "Remover do Hub" diz que o **post continua na rede** (alvo `published` não apagado) e, para alvo Incerto, que ele **pode** estar publicado; a de "Apagar na plataforma" diz que é **irreversível**

### AC-5: Apagar um post do Facebook
- **Dado** um alvo apagável do Facebook
- **Quando** o usuário confirma "Apagar na plataforma"
- **Então** o Hub chama `DELETE /{external_post_id}` com o **token da Página no header**, e com `{"success": true}` grava `deleted_at`, mantém o alvo `published`, mostra "Apagado na plataforma" e some o link; é logado `target_deleted platform=facebook result=ok`

### AC-6: Apagar um post do Threads
- **Dado** um alvo apagável do Threads
- **Quando** o usuário confirma
- **Então** o Hub renova o token se devido, chama `DELETE /{external_post_id}` em `graph.threads.com` e, com `{"success": true}`, grava `deleted_at` como no AC-5; o escopo `threads_delete` passa a fazer parte do login do Threads

### AC-7: Plataformas sem exclusão
- **Dado** um alvo do Instagram ou do WhatsApp
- **Quando** a tela é montada, ou um `POST` de apagar é feito direto
- **Então** não há botão "Apagar na plataforma" (aparece "Apague pelo app" com o link, quando existe) e o `POST` é recusado com mensagem, **sem chamar plataforma**

### AC-8: Elegibilidade
- **Dado** um alvo
- **Quando** ele **não** é `published`, não tem `external_post_id`, já está apagado, ou a conta foi desconectada ou está em `needs_reauth`
- **Então** "Apagar na plataforma" é recusado com o motivo, sem chamar plataforma (conta desconectada/reauth: o motivo diz para reconectar; a remoção do Hub continua possível)

### AC-9: Falha da plataforma
- **Dado** uma exclusão em andamento
- **Quando** a plataforma responde erro (token 102/190, permissão, limite, bloqueio, rede)
- **Então** o alvo **continua publicado e não apagado**, a mensagem é amigável (nunca o texto cru), erro de token marca a conta `needs_reauth`, e falta de `threads_delete` pede para **reconectar o Threads**

### AC-10: Resposta desconhecida
- **Dado** uma chamada de exclusão enviada
- **Quando** não há resposta (timeout/interrompido) ou ela é inválida depois de aceita
- **Então** **nada é gravado**, a mensagem diz que não foi possível confirmar e para conferir na rede, e o usuário pode tentar de novo com segurança

### AC-11: Objeto que já não existe
- **Dado** uma exclusão
- **Quando** a plataforma responde que o post não existe mais (apagado fora do Hub)
- **Então** o alvo é marcado como apagado (`deleted_at`) com mensagem informando que já havia sido apagado

### AC-12: Apagar a publicação inteira na plataforma
- **Dado** uma publicação com vários alvos
- **Quando** o usuário confirma "Apagar na plataforma (todos possíveis)"
- **Então** o Hub tenta cada alvo apagável, grava o resultado por alvo e mostra um resumo ("2 apagados, 1 falhou, 2 sem exclusão pelo Hub"); uma falha não impede os demais; nada é removido do Hub

### AC-13: Exibição do estado
- **Dado** um alvo apagado
- **Quando** o detalhe e o histórico são exibidos
- **Então** aparece "Apagado na plataforma" e a data, sem link para o post; o status geral da publicação não muda; o polling de estado não é afetado

### AC-14: Reconexão do Threads
- **Dado** o login do Threads
- **Quando** é iniciado
- **Então** o escopo é `threads_basic,threads_content_publish,threads_delete`; o README explica habilitar `threads_delete` no app Meta e reconectar contas antigas

### AC-15: Segurança
- **Dado** qualquer ação de excluir
- **Quando** é executada
- **Então** só aceita `POST` com CSRF; quem não é dono recebe **404** (nenhuma plataforma é chamada, nada é apagado); token, id externo, texto e corpo de resposta da plataforma **não** aparecem em logs, HTML nem mensagens; o token vai só no header

### AC-16: Imagem pública deixa de existir
- **Dado** uma publicação removida
- **Quando** a URL pública assinada (Threads/Instagram) é acessada
- **Então** a resposta é o 404 uniforme (a publicação já não existe)

### AC-17: Regressão e documentação
- **Dado** as specs 0002–0009
- **Quando** esta feature é entregue
- **Então** todos os seus critérios continuam passando; ADR-0014, glossário, README (remove "o Hub não exclui posts"), STATE e a nota na 0005/0009 sobre `external_post_id` são atualizados

## Matrizes de decisão

### Apagar na plataforma (por alvo)
| Plataforma | Status | `external_post_id` | Conta | Já apagado | Resultado | AC |
|------------|--------|--------------------|-------|------------|-----------|----|
| Facebook / Threads | published | sim | ativa | não | chama a API | AC-5, AC-6 |
| Facebook / Threads | published | sim | ativa | sim | recusa ("já apagado") | AC-8 |
| Facebook / Threads | published | não | — | — | recusa | AC-8 |
| Facebook / Threads | published | sim | desconectada / reauth | — | recusa (reconectar) | AC-8 |
| Facebook / Threads | pending, sending, failed, uncertain | — | — | — | recusa | AC-8 |
| Instagram / WhatsApp | qualquer | — | — | — | recusa ("Apague pelo app") | AC-7 |

### Resposta da plataforma
| Resposta | Resultado | AC |
|----------|-----------|----|
| sucesso | `deleted_at`; "Apagado" | AC-5, AC-6 |
| objeto inexistente | `deleted_at`; "já havia sido apagado" | AC-11 |
| token 102/190 | falha; conta `needs_reauth` | AC-9 |
| sem permissão / `threads_delete` | falha; pede reconexão | AC-9 |
| limite | falha; mensagem de limite | AC-9 |
| timeout / interrompido / inválida | nada gravado; "não foi possível confirmar" | AC-10 |

### Remover do Hub
| Situação | Resultado | AC |
|----------|-----------|----|
| nenhum alvo `sending` | remove publicação + imagem | AC-1 |
| algum alvo `sending` | recusa | AC-2 |
| alvo `pending` (sem `sending`) | removido junto (cancela) | AC-2 |
| remover um alvo que não é o último | só ele | AC-3 |
| remover o último alvo | remove a publicação e a imagem | AC-3 |
| não é o dono | 404 | AC-15 |

## Casos de borda e erros
- Imagem já inexistente no volume: a remoção do banco segue e a falha do arquivo é só logada.
- `external_post_id` vazio (container do Threads já `PUBLISHED` numa tentativa anterior): não dá para apagar pelo Hub (AC-8).
- Alvo Incerto: só "Remover do Hub" (com aviso); apagar na plataforma exige `published`.
- Limite de 100 exclusões/dia no Threads: mensagem de limite (AC-9).
- Publicação com alvos de contas já desconectadas: removível; apagar na plataforma recusa esses alvos (AC-8).

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Exclusão no **Instagram** e no **WhatsApp Status**.
- Lixeira, desfazer, exclusão agendada, exclusão em massa na lista.
- Editar posts; apagar comentários; apagar mídia fora das publicações do Hub.
- Confirmar no código o comportamento não documentado (posts criados fora do app no Facebook, códigos de "inexistente"): fica para o UAT.

## Rastreabilidade
- Product: `./product.md` · Design: `./design.md` · Domínio: `./domain.md` · Tasks: `./tasks.md`
- ADRs: [ADR-0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md), [ADR-0005](../../docs/architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md), [ADR-0011](../../docs/architecture/adr/0011-publicacao-em-segundo-plano-worker-no-banco-estado-incerto-e-recuperacao-sem-reenvio.md); novo ADR-0014 (task 1)
