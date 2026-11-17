---
name: spec
description: Contrato da feature 0002 — critérios de aceite para conectar Páginas do Facebook.
alwaysApply: true
---

# Spec — Conectar Página do Facebook

> **Fonte da verdade.** Status: implementado
> Os critérios de aceite são o contrato, o oráculo de teste e o prompt de implementação.

## Resumo
O Social Hub passa a permitir que um usuário autenticado conecte sua conta Meta, escolha uma ou várias Páginas do
Facebook, veja-as listadas, verifique o estado do token e as desconecte, guardando os tokens de forma segura.

## Critérios de aceite

### AC-1: Integração não configurada
- **Dado** que alguma variável `META_APP_ID`, `META_APP_SECRET`, `META_LOGIN_CONFIG_ID`, `META_REDIRECT_URI` ou `META_TOKEN_ENCRYPTION_KEY` está vazia
- **Quando** o usuário abre *Contas conectadas*
- **Então** vê "Integração com a Meta não configurada", o botão "Conectar Facebook" aparece desabilitado e `POST /contas/facebook/conectar/` não inicia o OAuth (volta à lista com mensagem)

### AC-2: Iniciar a conexão
- **Dado** a integração configurada e um usuário autenticado
- **Quando** ele envia `POST /contas/facebook/conectar/` (com CSRF)
- **Então** é gerado um `state` aleatório, guardado na sessão com validade de 10 minutos, e o usuário é redirecionado para `https://www.facebook.com/v27.0/dialog/oauth` com `client_id`, `config_id`, `redirect_uri`, `response_type=code`, `override_default_response_type=true` e o `state`; uma requisição GET a essa rota é recusada (405)

### AC-3: Callback válido leva à seleção de Páginas
- **Dado** um callback com `code` e `state` válido e a Meta devolvendo uma ou mais Páginas
- **Quando** o callback é processado
- **Então** o `code` é trocado por token de usuário de longa duração, `/me/accounts` é consultado, as Páginas (nome, categoria, imagem, tokens **criptografados**) ficam na sessão por 10 minutos, nenhuma `SocialAccount` é criada ainda e o usuário é redirecionado para `/contas/facebook/selecionar/`, que lista as Páginas com caixas de seleção e um controle "Marcar todas"

### AC-4: Conectar as Páginas selecionadas
- **Dado** a tela de seleção com Páginas pendentes na sessão
- **Quando** o usuário marca uma ou mais Páginas e confirma (`POST`)
- **Então** é criada uma `SocialAccount` com status `active` **apenas** para cada Página marcada, com o token criptografado; as demais são descartadas; a sessão pendente é limpa; o usuário vai para `/contas/` com mensagem de sucesso informando quantas Páginas foram conectadas

### AC-5: Reconectar uma Página já conectada
- **Dado** que o usuário já tem uma `SocialAccount` para a Página X (inclusive em `needs_reauth`)
- **Quando** ele a seleciona de novo e confirma
- **Então** a conta existente é **atualizada** (novo token, nome, categoria, status `active`, `last_error` vazio) sem criar duplicata

### AC-6: Usuário nega ou cancela a autorização
- **Dado** um callback com `error` (ex.: `access_denied`)
- **Quando** o callback é processado
- **Então** nenhuma chamada à Graph API é feita, nada é criado e o usuário volta a `/contas/` com mensagem amigável ("Autorização cancelada")

### AC-7: `state` inválido
- **Dado** um callback sem `state`, com `state` diferente do da sessão, expirado ou já utilizado
- **Quando** o callback é processado
- **Então** é rejeitado, nenhuma chamada à Graph API é feita, nada é criado, o evento `oauth_state_rejected` é logado e o usuário vê mensagem de erro genérica em `/contas/`

### AC-8: Falha da Meta
- **Dado** um callback com `state` válido
- **Quando** a troca de token ou `/me/accounts` falha (erro da Graph API, resposta inválida, `code` ausente ou timeout)
- **Então** nada é criado, o usuário vê mensagem genérica ("Não foi possível concluir a conexão com a Meta. Tente novamente."), o erro é logado (`graph_error` com código/endpoint) **sem** corpo de resposta nem credenciais

### AC-9: Nenhuma Página encontrada
- **Dado** um callback válido em que `/me/accounts` retorna lista vazia
- **Quando** o callback é processado
- **Então** o usuário volta a `/contas/` com a mensagem "Nenhuma Página encontrada nesta conta. Verifique se você administra uma Página e se a concedeu no login", e nada é criado

### AC-10: Seleção inválida
- **Dado** a tela de seleção
- **Quando** o usuário confirma sem marcar nada, com um ID que não pertence à lista pendente, ou com a sessão pendente ausente/expirada
- **Então** (sem marcação) a tela é exibida de novo com erro e nada é criado; (ID desconhecido) a requisição é rejeitada com mensagem de erro e nada é criado; (sessão expirada) o usuário volta a `/contas/` com a mensagem "A seleção expirou. Conecte novamente."

### AC-11: Listagem de contas
- **Dado** um usuário autenticado
- **Quando** abre `/contas/`
- **Então** vê **somente** as suas contas, cada uma com nome, categoria, status (`Ativa` / `Reconexão necessária`), data de conexão e as ações Verificar e Desconectar; sem nenhuma conta, vê o estado vazio com o botão de conectar; o token nunca é exibido

### AC-12: Verificar conta
- **Dado** uma conta do usuário
- **Quando** ele aciona Verificar (`POST`)
- **Então** o Hub consulta `GET /{page_id}` com o token da Página e: se OK, mantém `active` e atualiza `last_checked_at`; se a Meta responder token inválido/expirado/revogado (código 190), muda para `needs_reauth`, grava `last_error` resumido e mostra o aviso "Reconexão necessária"; em outro erro ou timeout, mantém o status e informa "Não foi possível verificar agora"

### AC-13: Desconectar conta
- **Dado** uma conta do usuário
- **Quando** ele aciona Desconectar (`POST`) e confirma
- **Então** a `SocialAccount` e o token são apagados do banco, a lista é atualizada com mensagem de sucesso, e uma requisição GET a essa rota é recusada (405)

### AC-14: Isolamento entre usuários
- **Dado** duas contas de usuário A e B
- **Quando** B tenta verificar ou desconectar uma conta de A (pela URL)
- **Então** recebe 404 e a conta de A permanece inalterada; B não vê contas de A na listagem

### AC-15: Dashboard reflete a conexão
- **Dado** a dashboard
- **Quando** o usuário tem ao menos uma `SocialAccount` `facebook_page` com status `active`
- **Então** o card do Facebook mostra "Conectado"; caso contrário (nenhuma conta, ou só `needs_reauth`), "Não conectado"; os demais números seguem demonstrativos

### AC-16: Segredos protegidos
- **Dado** qualquer etapa do fluxo
- **Quando** respostas HTML, mensagens, logs ou URLs das chamadas à Meta são inspecionados
- **Então** token de usuário, token de Página, `META_APP_SECRET` e `code` **não aparecem** em HTML, mensagens ou logs; o `client_secret` e o `code` trafegam em POST e os tokens em `Authorization: Bearer`; o token guardado no banco e na sessão **não é** texto puro (só descriptografa com `META_TOKEN_ENCRYPTION_KEY`)

### AC-17: Acesso restrito a usuários autenticados
- **Dado** um visitante anônimo
- **Quando** acessa qualquer rota desta feature (inclusive o callback)
- **Então** é redirecionado para o login e nada é processado

## Matriz de decisão

### Callback (`GET /contas/facebook/callback/`)
| `error` na URL | `state` válido | Troca de token e `/me/accounts` | Páginas devolvidas | Resultado esperado                                          | AC   |
|----------------|----------------|----------------------------------|--------------------|-------------------------------------------------------------|------|
| sim            | —              | — (não chama a Meta)             | —                  | Mensagem "Autorização cancelada"; nada criado               | AC-6 |
| não            | não            | — (não chama a Meta)             | —                  | Rejeita; loga `oauth_state_rejected`; nada criado           | AC-7 |
| não            | sim            | falha / `code` ausente / timeout | —                  | Mensagem genérica; loga `graph_error`; nada criado          | AC-8 |
| não            | sim            | ok                               | 0                  | Mensagem "Nenhuma Página encontrada"; nada criado           | AC-9 |
| não            | sim            | ok                               | ≥ 1                | Guarda na sessão (cifradas) e vai para a seleção            | AC-3 |

### Confirmação da seleção (`POST /contas/facebook/selecionar/`)
| Sessão pendente | IDs marcados                          | Resultado esperado                                          | AC    |
|-----------------|---------------------------------------|-------------------------------------------------------------|-------|
| ausente/expirada| —                                     | Volta a `/contas/` com "A seleção expirou"; nada criado     | AC-10 |
| válida          | nenhum                                | Reexibe a seleção com erro; nada criado                     | AC-10 |
| válida          | inclui ID fora da lista pendente      | Rejeita com erro; nada criado                               | AC-10 |
| válida          | ≥ 1, todos da lista, conta nova       | Cria `active` só das marcadas; limpa a sessão               | AC-4  |
| válida          | ≥ 1, todos da lista, conta existente  | Atualiza a existente (sem duplicar); limpa a sessão         | AC-5  |

### Verificação (`POST /contas/<id>/verificar/`)
| Resposta de `GET /{page_id}`        | Resultado esperado                                                       | AC    |
|-------------------------------------|--------------------------------------------------------------------------|-------|
| 200 OK                              | `active`, atualiza `last_checked_at`                                     | AC-12 |
| erro de token (código 190)          | `needs_reauth`, grava `last_error`, avisa para reconectar                | AC-12 |
| outro erro / timeout                | Mantém o status; "Não foi possível verificar agora"                      | AC-12 |

## Casos de borda e erros
- Página devolvida **sem** `access_token` (o usuário não tem papel suficiente): é ignorada na seleção e sinalizada como "sem permissão para gerenciar".
- Clique duplo ou reenvio do POST de seleção: idempotente (atualiza em vez de duplicar); a segunda requisição, sem sessão pendente, cai no caso "seleção expirou".
- Mesma Página conectada por **dois usuários diferentes**: permitido, cada um tem a sua `SocialAccount`.
- Nome/categoria com acentos ou emojis: persistidos e exibidos corretamente (UTF-8) e escapados no HTML.
- `redirect_uri` divergente do cadastrado na Meta: a Meta recusa o login; o usuário vê o caso AC-6/AC-8 e o log não expõe segredos.
- Chave de criptografia ausente ou inválida em uso: operações que dependem do token falham de forma controlada ("Integração com a Meta não configurada") sem erro 500.
- Timeout de rede com a Meta: limite de 10 s por chamada; sem retry automático nas chamadas de troca de token.

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Publicação, agendamento, insights/métricas reais, comentários e mensagens.
- Instagram e Threads.
- Webhooks e renovação automática de token em background.
- Revogar o app na Meta ao desconectar (só remoção local).
- App Review, Business Verification e modo Live do app Meta.
- Limitação de tentativas de login/callback além do `state` de uso único.
- Registro de `SocialAccount` no admin do Django (o token não deve ser exposto lá).
- Seleção de Página para publicação (feature futura; esta apenas deixa as contas disponíveis).

## Rastreabilidade
- Product: `./product.md`
- Design: `./design.md`
- Domínio: `./domain.md`
- ADRs relacionados: [ADR-0002](../../docs/architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md), [ADR-0003](../../docs/architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md)
