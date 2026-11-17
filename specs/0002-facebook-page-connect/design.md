---
name: design
description: Technical Design Doc da feature 0002 — conectar Páginas do Facebook (OAuth Meta, tokens criptografados, camada de serviço da Graph API).
alwaysApply: false
---

# Technical Design Doc — Conectar Página do Facebook

> **Tier:** arquitetural · **Status:** aprovado
> **Autor:** Thalyson · **Revisores:** — · **Data:** 2026-11-17
> Responde: **como** no nível de sistema. Veja o porquê em [`product.md`](./product.md).

## Links e artefatos

| Artefato                 | Onde        | Link                                         |
|--------------------------|-------------|----------------------------------------------|
| Página do design         | —           | (sem Confluence/Notion conectado)            |
| Issue / épico            | —           | (sem Jira/Linear conectado)                  |
| Spec · Product · Domínio | repositório | `./spec.md` · `./product.md` · `./domain.md` |
| App Meta                 | Meta for Developers | app "Social Hub Dev" (modo Desenvolvimento) |

## Contexto da funcionalidade
O Social Hub (Django 5.2, SQLite, Gunicorn, Docker) tem autenticação, dashboard demonstrativa e o app `social`
reservado com páginas placeholder (`apps/social/urls.py`). Esta é a primeira integração real. O app Meta já está
configurado com o caso de uso *Gerenciar Páginas*, as permissões `pages_show_list`, `pages_read_engagement`,
`pages_manage_posts`, `read_insights` e uma configuração de *Facebook Login for Business* (token de acesso do
usuário), que fornece um `config_id`. Esta feature entrega **conectar, listar e desconectar** Páginas.

## Goals / Non-goals
**Goals**
- Fluxo OAuth completo (autorização → token de usuário de longa duração → tokens das Páginas) com validação de `state`.
- Persistir cada Página como `SocialAccount` do usuário, com o token **criptografado** em repouso.
- Cliente fino da Graph API, com versão configurável, timeouts e erros tratados sem vazar segredos.
- Fundação reutilizável por Instagram e Threads (modelo e serviços não presos a "Facebook").

**Non-goals**
- Publicação, agendamento, insights reais, webhooks, App Review/modo Live, renovação em background.
- Revogar o app inteiro na Meta ao desconectar (ver Alternativas).

## Glossário (da funcionalidade)

| Termo               | Descrição                                                                                   |
|---------------------|---------------------------------------------------------------------------------------------|
| Conta social        | Uma identidade conectada numa rede (aqui: uma Página do Facebook), pertencente a um usuário. |
| Token de usuário    | Token OAuth da pessoa na Meta; usado só durante a conexão para descobrir as Páginas.         |
| Token de Página     | Token de acesso de uma Página, obtido via `/me/accounts`; é o que guardamos.                 |
| `config_id`         | ID da configuração do *Facebook Login for Business* (define permissões e tipo de token).     |
| Seleção de Páginas  | Tela pós-login onde o usuário marca quais Páginas conectar (uma ou várias).                  |
| `state`             | Valor aleatório de uso único que liga o início do login ao callback (proteção CSRF).         |
| Reconexão necessária | Estado de uma conta cujo token expirou, foi revogado ou perdeu permissão.                   |

## Design proposto

### Fluxo

```mermaid
sequenceDiagram
    actor U as Usuário
    participant H as Social Hub (Django)
    participant M as Meta (OAuth + Graph API)
    U->>H: POST /contas/facebook/conectar/ (CSRF)
    H->>H: gera state e guarda na sessão (TTL 10 min)
    H-->>U: 302 para diálogo OAuth (client_id, config_id, redirect_uri, state)
    U->>M: autoriza o app no diálogo da Meta
    M-->>U: 302 para redirect_uri com code e state
    U->>H: GET /contas/facebook/callback/?code=...&state=...
    H->>H: valida state (compare_digest, consumo único, TTL)
    H->>M: POST oauth/access_token (code) → token de usuário curto
    H->>M: POST oauth/access_token (fb_exchange_token) → token longo
    H->>M: GET me/accounts (Bearer token longo) → Páginas + tokens de Página
    H->>H: guarda as Páginas na sessão (tokens criptografados, TTL 10 min)
    H-->>U: 302 para /contas/facebook/selecionar/
    U->>H: POST com as Páginas marcadas (checkboxes)
    H->>H: upsert SocialAccount só das selecionadas; limpa a sessão
    H-->>U: 302 para /contas/ com mensagem de sucesso
```

- A **escolha das Páginas** acontece numa tela do Hub (`/contas/facebook/selecionar/`): lista de todas as
  Páginas devolvidas por `/me/accounts`, com caixas de seleção e "marcar todas", para conectar várias de uma vez.
  Só as marcadas viram `SocialAccount`. Depois, a desconexão é por Página; futuramente a publicação escolhe,
  entre as contas do usuário, em qual Página publicar.
- O token de usuário **não é persistido**: vive apenas na requisição do callback.
- As Páginas pendentes de seleção ficam **na sessão**, com o token de cada uma já **criptografado** (Fernet),
  e são descartadas ao confirmar, ao expirar (10 min) ou ao encerrar a sessão. Não há linhas "pendentes" no banco.
- Segredo (`client_secret`) e code vão em **POST**; tokens vão no header `Authorization: Bearer`, para não
  aparecerem em URLs, logs de proxy ou do `urllib3`.
- Ao concluir o callback, redirecionamos imediatamente, para que o `code` não fique no histórico/Referer.
- Erros do diálogo (`error`, `error_reason`) e do Graph (`code`/`subcode`) viram mensagens amigáveis; o corpo
  bruto da resposta não é exibido nem logado.

### Rotas (app `social`)

| Rota                              | Método | Nome                        | Função                                         |
|-----------------------------------|--------|-----------------------------|------------------------------------------------|
| `/contas/`                        | GET    | `social:accounts`           | Lista as contas do usuário (substitui o placeholder) |
| `/contas/facebook/conectar/`      | POST   | `social:facebook_connect`   | Inicia o OAuth                                 |
| `/contas/facebook/callback/`      | GET    | `social:facebook_callback`  | Recebe o code, busca as Páginas e guarda na sessão |
| `/contas/facebook/selecionar/`    | GET, POST | `social:facebook_select` | Escolha de uma ou mais Páginas; conecta as marcadas |
| `/contas/<id>/verificar/`         | POST   | `social:account_check`      | Testa o token (`GET /{page_id}`); atualiza status |
| `/contas/<id>/desconectar/`       | POST   | `social:account_disconnect` | Apaga a conta e o token local                  |

Todas exigem login (já global via `LoginRequiredMiddleware`) e filtram por `owner=request.user`
(outro usuário recebe 404).

### Modelo de dados (`apps/social/models.py`)

`SocialAccount`
| Campo               | Tipo                  | Notas                                                         |
|---------------------|-----------------------|---------------------------------------------------------------|
| `owner`             | FK → User             | `on_delete=CASCADE`                                           |
| `platform`          | CharField (choices)   | `facebook_page` agora; `instagram`, `threads` no futuro       |
| `external_id`       | CharField             | ID da Página na Meta                                          |
| `name`, `category`  | CharField             | Exibição                                                      |
| `picture_url`       | URLField (opcional)   | Exibição                                                      |
| `access_token_enc`  | TextField             | Token criptografado (Fernet); nunca exposto em `repr`/admin   |
| `granted_tasks`     | JSONField             | `tasks` devolvidas pela Meta (ex.: `CREATE_CONTENT`)          |
| `status`            | CharField (choices)   | `active` · `needs_reauth`                                     |
| `last_error`        | CharField (opcional)  | Código/resumo do último erro, **sem** dados sensíveis         |
| `connected_at`, `last_checked_at` | DateTime | Auditoria básica                                          |

Restrição única: (`owner`, `platform`, `external_id`). Reconectar a mesma Página **atualiza** a linha
(novo token, status `active`).

### Componentes

```
apps/social/
  models.py                 SocialAccount (+ set_token()/get_token())
  crypto.py                 Fernet/MultiFernet a partir de META_TOKEN_ENCRYPTION_KEY
  services/
    meta.py                 GraphClient: login_url(), exchange_code(), extend_token(),
                            list_pages(), get_page(); MetaApiError
    facebook_connect.py     fetch_pages(code) → Páginas p/ a sessão (tokens criptografados);
                            save_selected(user, pages, selected_ids) → upsert
  views.py                  AccountsView, FacebookConnectView, FacebookCallbackView, ...
  urls.py                   rotas acima
templates/social/accounts.html          lista + botões (substitui o placeholder de Contas)
templates/social/facebook_select.html   seleção de Páginas (checkboxes)
```

Integração com o resto: `apps/dashboard/demo.py::platforms()` passa a receber o conjunto de plataformas
conectadas pelo usuário (consulta a `SocialAccount`, status `active`) e marca "Conectado"; os números seguem demonstrativos.

### Configuração (variáveis de ambiente)

| Variável                  | Obrigatória | Descrição                                                        |
|---------------------------|-------------|------------------------------------------------------------------|
| `META_APP_ID`             | para a feature | ID do app Meta                                                |
| `META_APP_SECRET`         | para a feature | Segredo do app (só em `.env`, nunca versionado)               |
| `META_LOGIN_CONFIG_ID`    | para a feature | `config_id` da configuração de login                          |
| `META_GRAPH_VERSION`      | não         | Versão da Graph API; padrão `v27.0` (a mesma do app Meta)        |
| `META_REDIRECT_URI`       | para a feature | Deve coincidir **exatamente** com a URI cadastrada na Meta    |
| `META_TOKEN_ENCRYPTION_KEY` | para a feature | Chave(s) Fernet; várias separadas por vírgula permitem rotação |

Se algo faltar, o sistema **sobe normalmente** e a tela *Contas conectadas* exibe "Integração com a Meta não
configurada" com o botão desabilitado. `.env.example` e o README são atualizados.

## Cobertura dos 5 eixos

### 1. Tech stack
Novas dependências: **`requests`** (cliente HTTP síncrono, adequado aos workers sync do Gunicorn) e
**`cryptography`** (Fernet). Sem SDK da Meta. Sem mudança de Python/Django.

### 2. Arquitetura base
Fica no app `social`, em camadas: views finas → serviços (`facebook_connect`) → cliente (`GraphClient`) e
modelo. O cliente não conhece Django (recebe configuração e retorna dados simples), o que facilita o teste e a
reutilização por Instagram/Threads. Novo bounded context **Social (integrações)**; ver `domain.md`.

### 3. Infra
Sem novos serviços, volumes ou portas; o SQLite já persiste em `/data`. Novas variáveis chegam pelo `.env`
(`env_file` do compose). **Produção** exige HTTPS no `META_REDIRECT_URI` (proxy com TLS, `DJANGO_SECURE_SSL=true`).
**Reversão segura:** remover as variáveis desliga a feature; as migrations são reversíveis; a rota antiga
(placeholder) é o fallback se o template novo for revertido.

### 4. Qualidade
- Testes com `unittest.mock` sobre o transporte HTTP (sem rede), um teste por critério de aceite.
- Casos de erro: usuário nega, `state` inválido/expirado/reutilizado, Meta retorna erro, sem Páginas, token revogado (código 190), seleção vazia, seleção de ID que não veio da Meta (adulteração) e sessão pendente expirada.
- **Testes de segurança:** token nunca aparece no HTML, nas mensagens nem nos logs; token no banco e na sessão ≠ texto puro; usuário A não acessa conta do usuário B.
- `manage.py check` e `makemigrations --check` limpos; testes rodam no container (`docker compose exec web python manage.py test`).

### 5. Observabilidade
Logger `apps.social.meta` (JSON simples via formatter atual): eventos `oauth_started`, `oauth_state_rejected`,
`oauth_completed (pages=N)`, `graph_error (code, subcode, endpoint)`, `account_disconnected`. **Nunca** logar
URLs com query de token/segredo, corpos de resposta ou tokens. O `urllib3` fica em nível `WARNING`.
Prova de funcionamento: contagem de `oauth_completed` e ausência de `graph_error` na verificação de contas.

## Mapa de dependências

| Dependência                  | Tipo        | Descrição                                   | Endpoints / métodos                                                   |
|------------------------------|-------------|---------------------------------------------|-----------------------------------------------------------------------|
| Meta OAuth dialog            | OAuth 2.0   | Autorização do usuário (Login for Business) | `https://www.facebook.com/{v}/dialog/oauth` (`config_id`, `state`)    |
| Graph API                    | REST        | Troca de token e descoberta de Páginas      | `POST /oauth/access_token` · `GET /me/accounts` · `GET /{page-id}`    |
| `requests`                   | biblioteca  | HTTP síncrono com timeout                   | `Session.post/get`                                                    |
| `cryptography` (Fernet)      | biblioteca  | Criptografia autenticada dos tokens         | `Fernet`, `MultiFernet`                                               |
| Sessão do Django             | framework   | Guarda o `state` temporário                 | `request.session`                                                     |

## Solução

| #  | Bloco                                   | Descrição                                                              | Status     |
|----|-----------------------------------------|------------------------------------------------------------------------|------------|
| 1  | Settings + `.env.example`               | Variáveis `META_*`, validação de "configurado?"                        | definido   |
| 2  | `crypto.py`                             | Fernet/MultiFernet, helpers `encrypt/decrypt`                          | definido   |
| 3  | `models.py` + migration                 | `SocialAccount`, índice único, `set_token/get_token`                   | definido   |
| 4  | `services/meta.py`                      | `GraphClient` + `MetaApiError` (erros sanitizados)                     | definido   |
| 5  | `services/facebook_connect.py`          | Orquestra callback → upsert                                            | definido   |
| 6  | Views, URLs e templates                 | Fluxo, **seleção multi-Página**, listagem, verificar, desconectar      | definido   |
| 7  | Dashboard                               | Marca o Facebook como "Conectado" conforme `SocialAccount`             | definido   |
| 8  | Testes e documentação                   | Um teste por AC; README e `.env.example`                               | definido   |
| 9  | Versão da Graph API                     | Padrão `v27.0` (igual ao app Meta)                                     | definido   |

## Alternativas consideradas

| Alternativa                                         | Prós                                                    | Contras                                                         | Decisão |
|-----------------------------------------------------|---------------------------------------------------------|-----------------------------------------------------------------|---------|
| **A. OAuth com `config_id` + cliente próprio (`requests`)** | Alinhado ao Login for Business; poucas dependências; reutilizável | Mantemos o código do cliente                                    | **Escolhida** |
| B. OAuth clássico com `scope=`                      | Mais comum em tutoriais                                 | Não é o fluxo do Login for Business já configurado              | Não     |
| C. SDK/biblioteca de terceiros                      | Menos código                                            | Dependência extra; menos controle da versão da Graph API        | Não     |
| **D. Token de Página criptografado (Fernet) no SQLite** | Protege contra vazamento só do banco; rotação via MultiFernet | Chave no `.env` precisa de cuidado; perde-se a chave = reconectar | **Escolhida** |
| E. Token em texto puro                              | Simples                                                 | Vazamento do SQLite expõe as Páginas                            | Não     |
| F. Cofre externo (Vault/KMS)                        | Mais seguro                                             | Infra nova desproporcional para esta etapa                      | Futuro  |
| G. Conectar todas as Páginas que a Meta devolver    | Sem tela extra; sem tokens pendentes                    | Sem controle: usuário precisaria desconectar uma a uma          | Não (descartada pelo usuário) |
| **H. Tela própria de seleção (multi-seleção) pós-callback** | Escolhe várias de uma vez; base para escolher a Página ao publicar | Exige guardar tokens temporariamente | **Escolhida**; tokens na sessão, criptografados, TTL 10 min |
| H2. Persistir Páginas "pendentes" no banco          | Simples de ler                                          | Tokens de Páginas não escolhidas ficam no banco; exige limpeza  | Não     |
| **I. Desconectar = apagar localmente**              | Simples; não afeta outras conexões                      | O app continua autorizado na conta Meta até a pessoa remover    | **Escolhida** |
| J. Chamar `DELETE /me/permissions` ao desconectar   | Revoga de fato                                          | Revoga para **todas** as Páginas do usuário                     | Não     |

## Trade-offs e consequências
- **Ganhamos:** fundação segura e reutilizável, poucas dependências, fluxo sem tokens em URL/logs.
- **Aceitamos:** um passo a mais no fluxo (tela de seleção) e tokens pendentes temporariamente na sessão (criptografados); reconexão manual quando o token cair; revogação completa na Meta é feita pelo usuário.
- **Dívida assumida:** chave Fernet no `.env` (sem cofre); sem renovação em background; sem limite de tentativas no callback além do `state` de uso único.

## Riscos

| Risco                        | Descrição                                                          | Prob. × Impacto | Ações / mitigações                                                              |
|------------------------------|--------------------------------------------------------------------|-----------------|---------------------------------------------------------------------------------|
| Vazamento de token           | Token em log, URL, HTML ou backup do banco                         | baixa × alta    | Fernet, header Bearer, POST para segredo, testes de não-vazamento               |
| Perda da chave de criptografia | Tokens ilegíveis                                                 | média × média   | Documentar backup da chave; reconexão como recuperação; MultiFernet para rotação |
| Mudança na Graph API         | Campos/versão mudam                                                | média × média   | Versão fixada via env; erros sanitizados; testes com contrato mockado            |
| Redirect URI divergente      | Login quebra entre localhost e produção                            | alta × baixa    | `META_REDIRECT_URI` configurável; mensagem de erro clara; README                |
| Comportamento do `config_id` | Dialog/entrega do token difere do esperado em Login for Business   | média × média   | Spike no 1º teste real com a Página de teste (Questões em aberto)               |
| Tokens pendentes na sessão   | Sessão em DB guarda tokens de Páginas ainda não escolhidas         | baixa × média   | Criptografados (Fernet), TTL 10 min, descartados ao confirmar; IDs selecionados validados contra a lista da sessão |
| `state` reutilizado / CSRF   | Callback forjado                                                   | baixa × alta    | `state` aleatório, uso único, TTL, `compare_digest`                             |

## Roadmap da feature

| Fase / onda | Entrega                                                 | Quando   | Depende de |
|-------------|---------------------------------------------------------|----------|------------|
| 1 (MVP)     | Conectar, listar, verificar e desconectar Páginas       | esta feature | —       |
| 2           | Insights reais na dashboard (`read_insights`)           | próxima feature | 1    |
| 3           | Publicação e agendamento                                | depois   | 1          |

## Questões em aberto
- [x] **Versão da Graph API:** `v27.0`, a versão configurada no app Meta (decidido em 2026-11-17).
- [ ] **Spike com `config_id`:** confirmar, com a Página de teste, que o diálogo devolve `code` para `response_type=code` + `override_default_response_type=true` e que `/me/accounts` traz os tokens das Páginas.
- [ ] **Redirect URI de desenvolvimento:** confirmar `http://localhost:8080/contas/facebook/callback/` cadastrada na Meta (porta 8080 no `.env` local).

> Decisões difíceis de reverter → ADRs ao aprovar este design:
> **ADR-0002** Tokens de Página criptografados com Fernet (chave no `.env`) ·
> **ADR-0003** Integração Meta via OAuth `config_id` e cliente Graph próprio no app `social`.
