---
name: domain
description: Modelo DDD da feature 0002 — contexto Social (integrações), agregado SocialAccount.
alwaysApply: false
---

# Domain Model (DDD) — Conectar Página do Facebook

> Linguagem e modelo do negócio. Os termos abaixo aparecem iguais no código e no `docs/glossary.md`.

## Bounded Context
**Social (integrações)** — app Django `apps.social`. Subdomínio **core**: é o que diferencia o produto (falar com as
redes sociais em nome do usuário). A identidade do usuário (`accounts`) é **genérica**; a dashboard é **suporte**.

## Linguagem ubíqua

| Termo                  | Definição                                                                              | NÃO confundir com                     |
|------------------------|----------------------------------------------------------------------------------------|---------------------------------------|
| Conta social           | Identidade conectada numa rede (aqui, uma Página do Facebook) pertencente a um usuário. | Usuário do Social Hub (`User`)        |
| Página                 | Página do Facebook administrada pelo usuário na Meta.                                  | Perfil pessoal                        |
| Token de Página        | Credencial da Meta que permite agir como a Página; guardada criptografada.             | Token de usuário                      |
| Token de usuário       | Credencial da pessoa na Meta, usada só para descobrir as Páginas; não é persistida.    | Token de Página                       |
| Seleção de Páginas     | Passo em que o usuário marca quais Páginas conectar (uma ou várias).                   | Autorização na Meta                   |
| Conectar               | Criar/atualizar uma Conta social a partir de uma Página selecionada.                   | Autenticar no Social Hub (login)      |
| Desconectar            | Apagar a Conta social e o token localmente.                                            | Revogar o app na Meta                 |
| Reconexão necessária   | Estado da Conta social cujo token expirou, foi revogado ou perdeu permissão.           | Conta desconectada                    |
| `config_id`            | Identificador da configuração de login (permissões e tipo de token) na Meta.           | `app_id`                              |

## Agregados, entidades e value objects
- **Agregado `SocialAccount`** (raiz: `SocialAccount`)
  - Entidade: `SocialAccount` (dono, plataforma, `external_id`, nome, categoria, imagem, datas).
  - Value objects: `Platform` (`facebook_page`; `instagram`, `threads` no futuro), `ConnectionStatus`
    (`active` · `needs_reauth`), `EncryptedToken` (token cifrado com Fernet), `GrantedTasks` (tarefas da Meta).
  - **Invariantes:**
    1. (`owner`, `platform`, `external_id`) é único; reconectar a mesma Página **atualiza** a conta.
    2. O token é sempre armazenado criptografado e nunca exposto em representação, tela ou log.
    3. Só o dono lê, verifica ou desconecta a conta.
    4. Erro de autenticação da Meta (token inválido/revogado) leva a conta a `needs_reauth`, nunca a erro silencioso.
    5. Conta `active` possui token válido descriptografável.
  - Fronteira de consistência: uma conta, uma transação (conectar várias Páginas = uma transação por conta).
- **Sessão de conexão pendente** (não é agregado; estado temporário): Páginas devolvidas pela Meta aguardando
  seleção, com tokens criptografados, TTL de 10 min, descartada ao confirmar.

## Eventos de domínio
> Nesta etapa são eventos **lógicos** (registrados em log com o logger `apps.social.meta`); ainda sem barramento.

| Evento (passado)                    | Disparado quando                                           | Quem reage                          |
|-------------------------------------|------------------------------------------------------------|-------------------------------------|
| `ConexaoOAuthIniciada`              | Usuário inicia o login com a Meta                          | log                                 |
| `PaginasEncontradas`                | Callback válido devolve as Páginas do usuário              | tela de seleção                     |
| `ContaSocialConectada`              | Página selecionada é salva/atualizada                      | dashboard (marca "Conectado"), log  |
| `ContaSocialDesconectada`           | Usuário apaga a conta                                      | dashboard, log                      |
| `ContaSocialRequerReconexao`        | Verificação detecta token inválido/revogado                | tela de contas (alerta), log        |

## Relações com outros contextos
- **Social → Meta (Graph API):** **Anti-Corruption Layer** — `GraphClient` traduz a API da Meta para o modelo do
  Hub; o domínio não vê campos crus da Meta.
- **Social → Accounts (identidade):** **Conformist** — referencia o `User` do Django por chave estrangeira.
- **Social → Dashboard:** **Customer/Supplier** — a dashboard consulta as contas conectadas (somente leitura).
- Atualizado em `docs/architecture/context-map.md`.
