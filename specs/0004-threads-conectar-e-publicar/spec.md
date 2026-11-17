---
name: spec
description: Contrato da feature 0004 — conectar perfil do Threads e publicar texto, em alvos mistos com o Facebook.
alwaysApply: true
---

# Spec — Threads: conectar perfil e publicar texto

> **Fonte da verdade.** Status: aprovado
> Os critérios de aceite são o contrato, o oráculo de teste e o prompt de implementação.

## Resumo
O usuário conecta um perfil do Threads (login próprio, token de 60 dias com renovação sob demanda) e, no mesmo formulário da
0003, publica **texto** no Threads, sozinho ou junto com Páginas do Facebook (alvos mistos), com resultado por destino.

## Critérios de aceite

### AC-1: Threads não configurado
- **Dado** que `THREADS_APP_ID`, `THREADS_APP_SECRET` ou `THREADS_REDIRECT_URI` está vazio
- **Quando** o usuário abre *Contas conectadas*
- **Então** o botão "Conectar Threads" aparece desabilitado com o aviso "Integração com o Threads não configurada", `POST /contas/threads/conectar/` não inicia o OAuth, e o restante do sistema (Facebook) funciona normalmente

### AC-2: Iniciar a conexão
- **Dado** o Threads configurado e a requisição feita pelo host do `THREADS_REDIRECT_URI`
- **Quando** o usuário envia `POST /contas/threads/conectar/` (com CSRF)
- **Então** é gerado um `state` aleatório (sessão, validade de 10 minutos) e o usuário é redirecionado para `https://threads.com/oauth/authorize` com `client_id`, `redirect_uri`, `scope=threads_basic,threads_content_publish`, `response_type=code` e o `state`; `GET` a essa rota é recusado (405)

### AC-3: Aviso de host divergente
- **Dado** que o host da requisição difere do host do `THREADS_REDIRECT_URI` (ex.: `localhost` × domínio do túnel)
- **Quando** o usuário tenta conectar
- **Então** o OAuth **não** é iniciado e a mensagem "Acesse o Social Hub por {host} para conectar o Threads" é exibida em *Contas conectadas*

### AC-4: Callback válido conecta o perfil
- **Dado** um callback com `code` e `state` válidos
- **Quando** é processado
- **Então** o `code` é trocado por token curto e `user_id` (`POST`, com `client_secret` e `code` no corpo), o token curto vira token de longa duração com `expires_in`, o perfil é lido (`username`, nome) e é criada/atualizada uma `SocialAccount` `threads` (`external_id` = `user_id`) com o token **cifrado**, `token_expires_at` = agora + `expires_in`, `token_refreshed_at` = agora, status `active`; o usuário volta a `/contas/` com mensagem de sucesso e nenhuma tela de seleção

### AC-5: Reconectar o mesmo perfil
- **Dado** uma conta `threads` já existente do usuário para o mesmo `user_id` (inclusive `needs_reauth`)
- **Quando** ele conecta de novo
- **Então** a conta é **atualizada** (novo token, expiração, `username`, status `active`, `last_error` vazio), sem duplicar; conectar um perfil **diferente** cria outra conta

### AC-6: Usuário cancela a autorização
- **Dado** um callback com `error` (ex.: `access_denied`)
- **Quando** é processado
- **Então** nenhuma chamada à Threads API é feita, nada é criado e o usuário vê "Autorização cancelada" em `/contas/`

### AC-7: `state` inválido
- **Dado** um callback sem `state`, com `state` diferente, expirado ou já usado
- **Quando** é processado
- **Então** é rejeitado sem chamar a Threads API, nada é criado, é logado `threads_state_rejected` e o usuário vê mensagem genérica em `/contas/`

### AC-8: Falha da Meta na conexão
- **Dado** um callback com `state` válido
- **Quando** a troca do `code`, a troca por token longo ou a leitura do perfil falha (erro da API, resposta inválida, `code` ausente, timeout)
- **Então** nada é criado nem alterado, o usuário vê "Não foi possível concluir a conexão com o Threads. Tente novamente.", o erro é logado (`graph_error`) **sem** URL, parâmetros, corpo nem credenciais

### AC-9: Listagem de contas com validade
- **Dado** perfis do Threads conectados
- **Quando** o usuário abre *Contas conectadas*
- **Então** cada perfil mostra `@username`, plataforma, status e a validade do token ("expira em N dias"); um perfil cujo `token_expires_at` já passou aparece como "Reconexão necessária" (status atualizado **localmente**, sem chamada à rede); só as contas do próprio usuário aparecem e o token nunca é exibido

### AC-10: Verificar o perfil
- **Dado** uma conta `threads` do usuário
- **Quando** ele aciona Verificar (`POST`)
- **Então** o Hub aplica a renovação devida (AC-12) e lê o perfil: sucesso → `active` e `last_checked_at`; erro de token → `needs_reauth` com `last_error` resumido; outro erro/timeout → status inalterado e "Não foi possível verificar agora"

### AC-11: Desconectar o perfil
- **Dado** uma conta `threads` do usuário
- **Quando** ele aciona Desconectar (`POST`) e confirma
- **Então** a conta e o token são apagados do banco; os alvos de publicações antigas mantêm o snapshot (nome) e passam a "Conta desconectada"

### AC-12: Renovação do token sob demanda
- **Dado** uma conta `threads` prestes a publicar ou sendo verificada
- **Quando** a renovação é avaliada (matriz abaixo)
- **Então** só é chamado `th_refresh_token` se faltarem **menos de `THREADS_REFRESH_WINDOW_DAYS` (30)** para expirar **e** o token tiver **≥ 24 h** (`token_refreshed_at`); sucesso grava o novo token cifrado, `token_expires_at` (+60 dias) e `token_refreshed_at`; token já expirado → `needs_reauth` sem chamada; erro de token na renovação → `needs_reauth`; outro erro → mantém o token atual e segue

### AC-13: Formulário com destinos mistos
> **Atualizado pela [0006](../0006-whatsapp-status/spec.md) (AC-6):** o formulário ganha o grupo "Status do WhatsApp" (contas de instâncias da Evolution), com as mesmas regras de reconexão e de configuração.
- **Dado** um usuário com Páginas do Facebook e perfis do Threads
- **Quando** abre `/publicacoes/nova/`
- **Então** vê os destinos **ativos** agrupados por plataforma (rótulo/ícone), com caixas de seleção e "Marcar todas"; contas em "Reconexão necessária" aparecem desabilitadas com o aviso; a tela explica as regras ("Imagem obrigatória se marcar uma Página do Facebook · no Threads vai junto com o texto, até 500 — *0005*")

### AC-14: Imagem condicional
> **Atualizado pela [0006](../0006-whatsapp-status/spec.md) (AC-7):** a imagem segue obrigatória só com Página do Facebook; com **WhatsApp** ela é opcional e vai ao Status em base64 (sem exigir endereço público).
- **Dado** um formulário
- **Quando** há **Página do Facebook** marcada, **então** a imagem é obrigatória e validada/sanitizada como na 0003 (ausente ou inválida → erro, nada criado)
- **Quando** só há **perfis do Threads** marcados, **então** a imagem é opcional; se enviada, é validada e gravada e **vai ao Threads junto com o texto** (*atualizado pela [0005](../0005-threads-imagem/spec.md): antes era ignorada, com o aviso "No Threads, apenas o texto é publicado", que deixou de existir*)

### AC-15: Limites do texto por destino
- **Dado** um formulário com texto
- **Quando** há perfil do Threads marcado e o **peso** do texto excede 500 (cada caractere fora do BMP/emoji pesa 4) **ou** há mais de 5 links únicos
- **Então** o formulário é rejeitado com a mensagem do limite do Threads e nada é criado; sem Threads marcado vale o limite de 5000 caracteres da 0003; texto vazio continua inválido

### AC-16: Validação dos destinos
- **Dado** um formulário com texto (e imagem, quando exigida) válidos
- **Quando** nenhum destino é marcado, ou é marcado um destino inexistente, **de outro usuário** ou em "Reconexão necessária" (de qualquer plataforma)
- **Então** o formulário é rejeitado com erro e nada é criado nem enviado

### AC-17: Publicar texto no Threads
- **Dado** um alvo do Threads reivindicado para envio
- **Quando** ele é enviado
- **Então** a renovação é avaliada (AC-12); é criado o container (`POST /v1.0/{user_id}/threads`, `media_type=TEXT`, `text` no corpo) e o `id` é **gravado** no alvo (`external_container_id`); o Hub consulta o status do container até `FINISHED` (limite `THREADS_CONTAINER_WAIT_SECONDS`, padrão 20 s); publica (`POST /v1.0/{user_id}/threads_publish` com `creation_id`); lê o `permalink` (melhor esforço); o alvo fica `published` com `external_post_id` e link. **Vale para publicações sem imagem:** com imagem o container é `IMAGE` (*atualizado pela [0005](../0005-threads-imagem/spec.md)*)

### AC-18: Container que não fica pronto
- **Dado** um alvo do Threads
- **Quando** o container não chega a `FINISHED` dentro do limite, ou o status é `ERROR`/`EXPIRED` (matriz abaixo)
- **Então** o alvo fica `failed` com a mensagem amigável correspondente; se o container segue válido, o `external_container_id` é **mantido** e o próximo envio o **reutiliza** sem criar outro; em `ERROR`/`EXPIRED` o id é descartado e o próximo envio cria um novo

### AC-19: Container já publicado
- **Dado** um alvo cujo container já consta como `PUBLISHED` na consulta de status
- **Quando** o envio é retomado
- **Então** o alvo é marcado `published` **sem** republicar e sem link, e nenhuma segunda publicação é criada

### AC-20: Erros da Meta no envio ao Threads
- **Dado** um alvo do Threads sendo enviado
- **Quando** a Meta recusa (token inválido/expirado, limite, outro código), há erro de rede/timeout ou resposta inválida
- **Então** o alvo fica `failed` com a mensagem amigável (a mesma tabela da 0003: reconexão, limite, falha de comunicação, "A Meta recusou a publicação (código N)"), sem texto cru da Meta nem credenciais; erro de token marca a conta `needs_reauth`; erro de limite e de rede são reenviáveis; é logado `publish_failed platform=threads`

### AC-21: Alvos mistos
- **Dado** uma publicação com Páginas do Facebook **e** perfis do Threads
- **Quando** é enviada
- **Então** cada alvo segue o fluxo da **sua** plataforma (Facebook: foto + texto como na 0003; Threads: texto, e **imagem + texto** quando há imagem — *atualizado pela [0005](../0005-threads-imagem/spec.md)*), o resultado é por alvo (falha parcial permitida), o lote de até 5 alvos vale para todos juntos, "Continuar envio"/"Tentar novamente" reenviam só `pending`/`failed` e o comportamento do Facebook permanece **idêntico ao da 0003**

### AC-22: Idempotência e concorrência no Threads
> **Atualizado pela [0007](../0007-publicacao-em-segundo-plano/spec.md):** `sending` vencido (≥ 5 min) **não** é reivindicado de novo: vira **Incerto** e o container gravado é mantido para o "Reenviar" do usuário; só `pending` é reivindicado, em ambos os modos (`worker` e `inline`).
- **Dado** o mesmo alvo do Threads
- **Quando** duas requisições tentam enviá-lo ao mesmo tempo, ou ele já está `published`, ou `sending` há menos de 5 minutos
- **Então** só **uma** reivindica e chama a Meta; `published` nunca é reenviado; `sending` ≥ 5 min é reivindicado de novo e retoma pelo `external_container_id` (log `target_reclaimed`)

### AC-23: Histórico e detalhe sem imagem
- **Dado** uma publicação só do Threads (sem imagem)
- **Quando** o usuário abre `/publicacoes/` ou `/publicacoes/<id>/`
- **Então** um ícone ocupa o lugar da imagem, `/publicacoes/<id>/imagem/` responde 404, cada alvo mostra a plataforma, o status e o link do post (quando `published`) ou o motivo (quando `failed`), e publicações antigas do Facebook continuam exibindo a imagem

### AC-24: Dashboard
- **Dado** a dashboard
- **Quando** o usuário tem ao menos uma conta `threads` com status `active`
- **Então** o Threads aparece como "Conectado"; sem conta ou só com `needs_reauth`, como "Não conectado"

### AC-25: Segredos e conteúdo protegidos
- **Dado** qualquer etapa de conexão, renovação ou publicação
- **Quando** HTML, mensagens, logs e URLs/parâmetros registrados são inspecionados
- **Então** token curto, token longo, `THREADS_APP_SECRET`, `code` e o **texto da publicação** não aparecem em HTML, mensagens nem logs; o Hub **não registra URLs, parâmetros nem corpos** das chamadas; o token guardado no banco **não é** texto puro

### AC-26: Acesso e isolamento
- **Dado** um visitante anônimo, ou o usuário B diante de contas/publicações do usuário A
- **Quando** acessam rotas da feature
- **Então** o anônimo é levado ao login sem nada processado; B recebe 404 ao verificar/desconectar contas de A e não as vê na listagem nem no formulário

### AC-27: Atualização da spec 0003
- **Dado** a spec 0003
- **Quando** esta feature é implementada
- **Então** a 0003 é atualizada: **AC-1** (formulário passa a listar também perfis do Threads) e **AC-5** (imagem obrigatória **somente** quando há Página do Facebook entre os destinos) refletem as regras acima; os testes `test_AC_1_*` e `test_AC_5_*` da 0003 são ajustados; todos os demais critérios da 0003 continuam passando sem alteração

## Matriz de decisão

### Callback do Threads (`GET /contas/threads/callback/`)
| `error` na URL | `state` válido | Troca do code, token longo e perfil | Resultado esperado                                         | AC   |
|----------------|----------------|--------------------------------------|------------------------------------------------------------|------|
| sim            | —              | — (não chama a API)                  | "Autorização cancelada"; nada criado                       | AC-6 |
| não            | não            | — (não chama a API)                  | Rejeita; loga `threads_state_rejected`; nada criado        | AC-7 |
| não            | sim            | falha / `code` ausente / timeout     | Mensagem genérica; nada criado/alterado                    | AC-8 |
| não            | sim            | ok                                   | Cria/atualiza a conta `threads`; volta a `/contas/`        | AC-4, AC-5 |

### Criação com destinos mistos (`POST /publicacoes/nova/`)
| Destinos marcados        | Imagem   | Texto                               | Resultado esperado                                              | AC            |
|--------------------------|----------|-------------------------------------|-----------------------------------------------------------------|---------------|
| só Facebook              | ausente  | —                                   | Erro: imagem obrigatória; nada criado                           | AC-14         |
| só Facebook              | válida   | > 5000                              | Erro de limite de texto; nada criado                            | AC-15         |
| só Facebook              | válida   | válido                              | Cria e envia como na 0003                                       | AC-21         |
| só Threads               | ausente  | peso ≤ 500 e ≤ 5 links              | Cria **sem imagem** e envia o 1º lote                           | AC-14, AC-17  |
| só Threads               | enviada  | peso ≤ 500 e ≤ 5 links              | Cria sem imagem (imagem ignorada, com aviso) e envia            | AC-14         |
| só Threads               | —        | peso > 500                          | Erro: limite do Threads; nada criado                            | AC-15         |
| só Threads               | —        | > 5 links únicos                    | Erro: limite de links; nada criado                              | AC-15         |
| Facebook + Threads       | ausente  | —                                   | Erro: imagem obrigatória (há Página); nada criado               | AC-14         |
| Facebook + Threads       | válida   | peso > 500                          | Erro: limite do Threads; nada criado                            | AC-15         |
| Facebook + Threads       | válida   | peso ≤ 500 e ≤ 5 links              | Cria e envia os dois tipos de alvo                              | AC-21         |
| qualquer                 | —        | —, com destino inválido/nenhum      | Erro de seleção; nada criado                                    | AC-16         |

### Renovação do token (`ensure_fresh`)
| Expiração   | Tempo restante | Idade do token | Resultado esperado                                              | AC    |
|-------------|----------------|----------------|-----------------------------------------------------------------|-------|
| já passou   | —              | —              | `needs_reauth`, sem chamada à rede                              | AC-12 |
| futura      | ≥ 30 dias      | —              | Nada a fazer (não chama `th_refresh_token`)                     | AC-12 |
| futura      | < 30 dias      | < 24 h         | Nada a fazer (cedo demais)                                      | AC-12 |
| futura      | < 30 dias      | ≥ 24 h         | Renova: novo token, nova expiração (+60 dias), `refreshed_at`   | AC-12 |
| (renovação) | erro de token  | —              | `needs_reauth`                                                  | AC-12 |
| (renovação) | outro erro     | —              | Mantém o token atual e segue                                    | AC-12 |

### Envio ao Threads (container)
| Estado do alvo / status do container        | Ação                                                                  | AC    |
|---------------------------------------------|-----------------------------------------------------------------------|-------|
| sem `external_container_id`                 | Cria o container, grava o id, passa a esperar                         | AC-17 |
| com id (container válido)                   | Reutiliza o container                                                 | AC-18 |
| `IN_PROGRESS` dentro do limite de espera    | Continua consultando                                                  | AC-17 |
| `IN_PROGRESS` e o limite acabou             | `failed` reenviável ("ainda está processando"); mantém o id           | AC-18 |
| `FINISHED`                                  | Publica; lê o permalink; `published`                                  | AC-17 |
| `ERROR`                                     | `failed`; descarta o id                                               | AC-18 |
| `EXPIRED`                                   | `failed` reenviável; descarta o id (próximo envio cria outro)         | AC-18 |
| `PUBLISHED`                                 | `published` sem link; **não** republica                               | AC-19 |

## Casos de borda e erros
- O `username` pode mudar no Threads: a reconexão ou o Verificar o atualiza; o histórico usa o snapshot.
- Mesmo perfil do Threads conectado por **dois usuários** do Hub: permitido (uma conta para cada).
- Links repetidos no texto contam **uma vez**; o limite é de 5 links **únicos**.
- Emoji, acentos e quebras de linha: preservados e **escapados** na exibição; o peso só afeta a validação.
- Texto só com espaços é inválido; o limite de 500 (peso) é **conservador** (a Meta pode contar diferente e recusar; nesse caso vale AC-20).
- `redirect_uri` divergente do cadastrado, ou túnel com URL nova: a Meta recusa o login; vale AC-6/AC-8 e o README explica como atualizar.
- Perfil privado ou convite de testador não aceito: o login falha na Meta; vale AC-6/AC-8.
- Migração: publicações da 0003 existentes continuam com imagem; novas publicações só-Threads têm `image` vazio.
- Limite de 250 publicações por 24 h por perfil: o erro da Meta vira a mensagem de limite (AC-20), reenviável.

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- ~~Imagem~~ (entregue pela [0005](../0005-threads-imagem/spec.md)), vídeo, carrossel, GIF e enquete no Threads; respostas, menções, insights e `topic_tag`/`link_attachment`.
- Instagram.
- Agendamento, fila/worker e renovação de token em segundo plano.
- Perfis privados do Threads.
- Tratamento real dos callbacks de **desinstalação** e **exclusão de dados** (ficam vazios no app Meta).
- Publicação de **só texto no Facebook** (continua exigindo imagem quando há Página do Facebook).
- Verificação anti-duplicidade ao reenviar `sending` preso no Facebook (issue [#1](https://github.com/thalisonwilker/social-hub/issues/1)).

## Rastreabilidade
- Product: `./product.md`
- Design: `./design.md`
- Domínio: `./domain.md`
- ADRs relacionados: [ADR-0006](../../docs/architecture/adr/0006-threads-cliente-proprio-token-60-dias-renovacao-sob-demanda.md), [ADR-0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md), [ADR-0002](../../docs/architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md), [ADR-0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md)
- Features base: [`0002-facebook-page-connect`](../0002-facebook-page-connect/spec.md) · [`0003-publicar-no-facebook`](../0003-publicar-no-facebook/spec.md)
