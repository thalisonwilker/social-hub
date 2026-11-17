---
name: spec
description: Contrato da feature 0003 — critérios de aceite para publicar texto + imagem em várias Páginas do Facebook.
alwaysApply: true
---

# Spec — Publicar no Facebook (texto + imagem, várias Páginas)

> **Fonte da verdade.** Status: rascunho
> Os critérios de aceite são o contrato, o oráculo de teste e o prompt de implementação.

## Resumo
O usuário cria uma publicação com **texto e uma imagem**, escolhe **uma ou mais Páginas** conectadas e a publica de uma vez,
vendo o resultado de cada Página, podendo repetir só as que falharam e consultando o histórico.

## Critérios de aceite

### AC-1: Formulário e seleção de Páginas
- **Dado** um usuário com Páginas conectadas
- **Quando** abre `/publicacoes/nova/`
- **Então** vê os campos de texto e imagem e a lista das suas Páginas **ativas** com caixas de seleção e um controle "Marcar todas"; contas em "Reconexão necessária" aparecem desabilitadas com o aviso e o link para reconectar; o botão de publicar pede confirmação ("Será publicado de verdade nas Páginas selecionadas") e fica desabilitado após o envio do formulário

### AC-2: Sem Páginas ativas ou integração não configurada
- **Dado** que o usuário não tem Página ativa, **ou** que a integração com a Meta não está configurada
- **Quando** abre `/publicacoes/nova/`
- **Então** vê a explicação e o link para *Contas conectadas*, o formulário de envio não é oferecido e um `POST` a essa rota não cria nada nem chama a Meta

### AC-3: Publicar com sucesso em uma ou mais Páginas
- **Dado** um formulário válido com N Páginas ativas do usuário
- **Quando** ele envia (`POST` com CSRF)
- **Então** são criados a `Publication` e um alvo por Página; para cada alvo (no limite do lote, ver AC-11) o Hub chama `POST /{page_id}/photos` em **multipart** (`source` = imagem sanitizada, `message` = texto, `published=true`) com o token da Página no header `Authorization`; em sucesso o alvo vira `published` com `post_id` e link; o usuário é levado a `/publicacoes/<id>/` com o resultado de cada Página

### AC-4: Validação do texto
- **Dado** um formulário
- **Quando** o texto está vazio (ou só espaços) ou tem mais de 5000 caracteres
- **Então** o formulário é reexibido com o erro, o conteúdo digitado é mantido, e **nada** é criado nem enviado

### AC-5: Validação da imagem
- **Dado** um formulário
- **Quando** a imagem está ausente, não é uma imagem de verdade (ex.: `.jpg` com conteúdo de outro tipo), não é JPEG/PNG (ex.: GIF, WebP, SVG), passa de 8 MiB ou excede 40 milhões de pixels
- **Então** o formulário é reexibido com o erro apropriado e **nada** é criado nem enviado

### AC-6: Imagem sanitizada e guardada com segurança
- **Dado** uma imagem válida
- **Quando** a publicação é criada
- **Então** o arquivo guardado foi **re-encodado** (formato real JPEG ou PNG), **sem EXIF/metadados** (a orientação é aplicada antes), com **nome aleatório** que não contém o nome original, dentro de `MEDIA_ROOT/publications/`; é esse arquivo que segue para a Meta

### AC-7: Validação da seleção de Páginas
- **Dado** um formulário com texto e imagem válidos
- **Quando** nenhuma Página é marcada, ou é marcada uma conta inexistente, **de outro usuário** ou em "Reconexão necessária"
- **Então** o formulário é rejeitado com erro e **nada** é criado nem enviado

### AC-8: Falha parcial
- **Dado** uma publicação em várias Páginas
- **Quando** o envio a uma Página falha e as demais têm sucesso
- **Então** as bem-sucedidas ficam `published`, a que falhou fica `failed` com o motivo amigável, o status geral é "Com falhas" e o resultado por Página é exibido

### AC-9: Token inválido durante o envio
- **Dado** um alvo sendo enviado
- **Quando** a Meta responde erro de token (código 190 ou 102)
- **Então** o alvo fica `failed` com "Reconexão necessária para esta Página.", a `SocialAccount` passa a `needs_reauth` e os demais alvos do lote seguem normalmente

### AC-10: Demais erros da Meta
- **Dado** um alvo sendo enviado
- **Quando** a Meta recusa (permissão, limite, bloqueio, outro código), há erro de rede/timeout ou a resposta é inválida
- **Então** o alvo fica `failed` com a mensagem amigável correspondente (tabela do design), **sem** o texto cru da Meta e sem credenciais, e o erro é logado (`publish_failed` com Página e código)

### AC-11: Envio em lotes
- **Dado** uma publicação com mais de 5 alvos
- **Quando** é criada ou quando o usuário aciona "Continuar envio" (`POST /publicacoes/<id>/enviar/`)
- **Então** cada requisição envia **no máximo 5** alvos pendentes; os restantes permanecem `pending` e o detalhe indica quantos faltam

### AC-12: Tentar de novo sem duplicar
- **Dado** uma publicação com alvos `published`, `failed` e `pending`
- **Quando** o usuário aciona "Tentar novamente" / "Continuar envio"
- **Então** só os alvos `failed` e `pending` são enviados; alvos `published` **nunca** são reenviados (nenhuma chamada à Meta para eles)

### AC-13: Concorrência e recuperação
- **Dado** duas requisições simultâneas de envio para o mesmo alvo
- **Quando** ambas tentam reivindicá-lo
- **Então** exatamente **uma** chama a Meta (claim atômico); um alvo `sending` com menos de 5 minutos **não** é reenviado; um alvo `sending` com 5 minutos ou mais é reivindicado de novo e enviado (log `target_reclaimed`)

### AC-14: Conta desconectada
- **Dado** um alvo cuja conta foi desconectada depois da criação
- **Quando** o envio é tentado
- **Então** o alvo fica `failed` com "Conta desconectada.", **não** é reenviável e o histórico continua exibindo o nome da Página (snapshot)

### AC-15: Histórico
- **Dado** um usuário autenticado
- **Quando** abre `/publicacoes/`
- **Então** vê **somente** as suas publicações, da mais recente para a mais antiga, cada uma com resumo do texto, miniatura, data, status geral (Publicada · Com falhas · Pendente) e contagem por status; sem publicações, vê o estado vazio com o botão "Nova publicação"

### AC-16: Detalhe da publicação
- **Dado** uma publicação do usuário
- **Quando** abre `/publicacoes/<id>/`
- **Então** vê texto completo (escapado), imagem, e por Página: nome, status, link do post (se `published`) ou motivo (se `failed`); o botão de reenvio aparece só se houver alvos `failed` reenviáveis ou `pending`

### AC-17: Imagem protegida
- **Dado** uma publicação com imagem
- **Quando** `/publicacoes/<id>/imagem/` é acessada
- **Então** o dono recebe o arquivo com o `Content-Type` correto e `X-Content-Type-Options: nosniff`; outro usuário recebe 404; anônimo é levado ao login; **não existe** URL pública de mídia (`/media/…` retorna 404)

### AC-18: Isolamento entre usuários
- **Dado** publicações dos usuários A e B
- **Quando** B tenta ver, enviar ou baixar a imagem de uma publicação de A (por ID)
- **Então** recebe 404 e nada muda; B não vê publicações de A no histórico

### AC-19: Segredos e conteúdo fora de logs
- **Dado** qualquer etapa da publicação
- **Quando** HTML, mensagens, logs e URLs são inspecionados
- **Então** token da Página, `META_APP_SECRET` e o **texto da publicação** não aparecem em logs; tokens não aparecem em HTML, mensagens nem URLs; o token vai só no header `Authorization`

### AC-20: Acesso autenticado e métodos
- **Dado** um visitante anônimo
- **Quando** acessa qualquer rota da feature
- **Então** é levado ao login e nada é processado; `/publicacoes/<id>/enviar/` recusa `GET` (405); criar e enviar exigem CSRF

## Matriz de decisão

### Criação (`POST /publicacoes/nova/`)
| Texto (1–5000)  | Imagem válida (JPEG/PNG, ≤ 8 MiB, ≤ 40 MP) | Páginas marcadas                                  | Resultado esperado                                          | AC   |
|-----------------|---------------------------------------------|---------------------------------------------------|-------------------------------------------------------------|------|
| inválido        | —                                           | —                                                 | Erro no texto; nada criado nem enviado                      | AC-4 |
| válido          | não                                         | —                                                 | Erro na imagem; nada criado nem enviado                     | AC-5 |
| válido          | sim                                         | nenhuma                                           | Erro de seleção; nada criado nem enviado                    | AC-7 |
| válido          | sim                                         | inclui conta inexistente / de outro / `needs_reauth` | Rejeita; nada criado nem enviado                          | AC-7 |
| válido          | sim                                         | ≥ 1 conta ativa do usuário                        | Cria publicação + alvos; imagem sanitizada; envia 1º lote   | AC-3 |

### Resultado do envio de um alvo
| Resposta / situação                          | Alvo         | Conta        | Mensagem amigável                                   | AC    |
|----------------------------------------------|--------------|--------------|-----------------------------------------------------|-------|
| sucesso (`id` e `post_id`)                   | `published`  | —            | —                                                   | AC-3  |
| erro 190 / 102                               | `failed`     | `needs_reauth` | "Reconexão necessária para esta Página."          | AC-9  |
| erro 10 / 200 / 220                          | `failed`     | —            | "Sem permissão para publicar nesta Página."         | AC-10 |
| erro 4 / 17 / 32 / 613                       | `failed` (reenviável) | —   | "Limite de requisições da Meta. Tente mais tarde."  | AC-10 |
| erro 368                                     | `failed`     | —            | "A Meta bloqueou esta publicação."                  | AC-10 |
| rede / timeout / resposta inválida           | `failed` (reenviável) | —   | "Falha de comunicação com a Meta."                  | AC-10 |
| outro código N                               | `failed`     | —            | "A Meta recusou a publicação (código N)."           | AC-10 |
| conta nula (desconectada)                    | `failed` (**não** reenviável) | — | "Conta desconectada."                         | AC-14 |

### Reivindicação do alvo (envio / reenvio)
| Estado atual do alvo                  | Último envio     | Ação                                                    | AC    |
|---------------------------------------|------------------|---------------------------------------------------------|-------|
| `pending`                             | —                | Reivindica e envia (se ainda couber no lote)            | AC-11 |
| `failed` com conta existente          | —                | Reivindica e envia (retry)                              | AC-12 |
| `failed` com conta nula               | —                | Não envia (continua `failed`)                           | AC-14 |
| `sending`                             | < 5 min          | Não envia (outra requisição o tem)                      | AC-13 |
| `sending`                             | ≥ 5 min          | Reivindica de novo e envia; loga `target_reclaimed`     | AC-13 |
| `published`                           | —                | **Nunca** envia                                         | AC-12 |

## Casos de borda e erros
- Texto com emoji, acentos, quebras de linha e HTML: preservado e **escapado** na exibição; enviado como veio à Meta.
- PNG com transparência permanece PNG; JPEG com orientação EXIF é rotacionado corretamente antes de remover metadados.
- GIF animado, WebP e SVG são rejeitados (apenas JPEG/PNG reais). Extensão enganosa não vale: vale o formato real.
- Mesma imagem enviada duas vezes cria duas publicações independentes (sem deduplicação entre publicações).
- Envio duplo do formulário: o botão é desabilitado no clique; mesmo assim, dois envios criam duas publicações, mas **nunca** dois posts por (publicação × Página).
- Queda do processo entre a Meta publicar e o Hub gravar `published`: o alvo fica `sending` e, após 5 min, pode gerar post duplicado — **janela aceita e rastreada na issue [#1](https://github.com/thalisonwilker/social-hub/issues/1)**.
- Disco cheio / erro ao gravar a imagem: nada é criado (transação) e o usuário vê "Não foi possível salvar a publicação".
- Página sem a tarefa de criar conteúdo: **sem pré-checagem**; a Meta recusa e o alvo mostra a mensagem de permissão.

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Agendamento, fila/worker e execução em background.
- Rascunhos; editar ou excluir o post na Meta; excluir publicação do histórico.
- Mais de uma imagem, vídeo, publicação só de texto.
- Instagram e Threads.
- Insights do post e contagens na dashboard.
- Verificação anti-duplicidade antes de reenviar `sending` preso (issue #1).
- Pré-checagem de permissão de publicar (`CREATE_CONTENT`).
- Limpeza automática de imagens antigas; armazenamento externo (S3).

## Rastreabilidade
- Product: `./product.md`
- Design: `./design.md`
- Domínio: `./domain.md`
- ADRs relacionados: [ADR-0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md), [ADR-0005](../../docs/architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md)
- Feature base: [`0002-facebook-page-connect`](../0002-facebook-page-connect/spec.md) · Issue relacionada: [#1](https://github.com/thalisonwilker/social-hub/issues/1)
