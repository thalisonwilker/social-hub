---
name: domain
description: Modelo DDD da feature 0003 — agregado Publication com PublicationTarget no contexto Social.
alwaysApply: false
---

# Domain Model (DDD) — Publicar no Facebook

> Linguagem e modelo do negócio; os termos aparecem iguais no código e em `docs/glossary.md`.

## Bounded Context
**Social (integrações)** (o mesmo da 0002, `apps.social`), subdomínio **core**. Esta feature acrescenta o agregado de
**publicação**; a Página continua sendo a `SocialAccount` da 0002.

## Linguagem ubíqua

| Termo               | Definição                                                                                      | NÃO confundir com                    |
|---------------------|------------------------------------------------------------------------------------------------|--------------------------------------|
| Publicação          | Conteúdo (texto + 1 imagem) que o usuário quer publicar em uma ou mais Páginas.                 | Post (resultado criado na Meta)      |
| Alvo da publicação  | Par (Publicação, Página) com o estado e o resultado do envio àquela Página.                     | Conta social                         |
| Post                | O que a Meta cria no Facebook; identificado por `post_id` e link permanente.                   | Publicação                           |
| Publicar            | Enviar o conteúdo de um alvo à Meta e registrar o resultado.                                   | Conectar (0002)                      |
| Tentar de novo      | Reenviar apenas os alvos `failed` (ou `pending`), nunca os `published`.                        | Republicar                           |
| Lote                | Conjunto de até 5 alvos enviados numa requisição.                                              | Publicação                           |
| Reivindicar         | Marcar atomicamente um alvo como `sending` para que só uma requisição o envie.                 | Bloquear                             |

## Agregados, entidades e value objects
- **Agregado `Publication`** (raiz: `Publication`)
  - Entidades: `Publication` (dono, texto, imagem, data) e `PublicationTarget` (Página, estado, resultado).
  - Value objects: `TargetStatus` (`pending` · `sending` · `published` · `failed`), `PageSnapshot` (ID e nome da Página no momento
    da publicação), `PostRef` (`post_id` + link), `FriendlyError` (mensagem amigável + código da Meta).
  - **Invariantes:**
    1. Texto de 1 a 5000 caracteres e **exatamente uma** imagem válida e sanitizada.
    2. Pelo menos um alvo; no máximo um alvo por Página na mesma publicação.
    3. Só Páginas **ativas do próprio dono** podem ser alvo na criação.
    4. Alvo `published` é **imutável** e nunca é reenviado.
    5. Um alvo só é enviado se foi **reivindicado** (`sending`) por exatamente uma requisição.
    6. O alvo guarda **snapshot** da Página: o histórico sobrevive à desconexão da conta.
    7. Mensagens de erro são amigáveis; o corpo cru da Meta e os tokens nunca são persistidos nem exibidos.
    8. O status geral da publicação é **derivado** dos alvos (nunca armazenado).
  - Fronteira de consistência: a criação (publicação + imagem + alvos) é uma transação; **cada alvo** é uma unidade
    independente no envio (um alvo falhar não afeta os outros).

## Eventos de domínio
> Eventos **lógicos** registrados em log (`apps.social.meta`); ainda sem barramento.

| Evento (passado)          | Disparado quando                                           | Quem reage                                  |
|---------------------------|------------------------------------------------------------|---------------------------------------------|
| `PublicacaoCriada`        | Formulário válido salvo                                    | log                                         |
| `AlvoReivindicado`        | Alvo muda para `sending`                                   | log                                         |
| `AlvoPublicado`           | Meta devolve o post                                        | histórico, log                              |
| `AlvoFalhou`              | Meta recusa, rede falha ou timeout                         | histórico, log                              |
| `ContaRequerReconexao`    | Erro de token durante o envio                              | Conta (0002) passa a `needs_reauth`         |
| `AlvoRecuperado`          | `sending` antigo é reivindicado de novo                    | log (ver issue #1)                          |

## Relações com outros contextos
- **Publicação → Conta social (0002):** o alvo referencia `SocialAccount` (`SET_NULL`); a publicação lê o token cifrado e pode mudar
  o status da conta (`needs_reauth`). Mesmo bounded context, relação de dependência direta.
- **Social → Meta (Graph API):** **Anti-Corruption Layer** (`GraphClient.publish_photo`); o domínio não vê a resposta crua.
- **Social → Identidade:** **Conformist** (FK para `User`), como na 0002.
- **Social → Painel:** a dashboard poderá consumir contagens de publicações (fora desta entrega).
