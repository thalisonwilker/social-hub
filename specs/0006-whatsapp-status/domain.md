---
name: domain
description: Modelo DDD da feature 0006 — plataforma WhatsApp (Status) via Evolution API: conta = instância, envio único, sem link, estado de conexão.
alwaysApply: false
---

# Domain Model (DDD) — WhatsApp: publicar no Status via Evolution API

> Evolui `SocialAccount`/`Publication`/`PublicationTarget` (0002–0005) no contexto **Social (integrações)**, subdomínio **core**.

## Bounded Context
**Social (integrações)** (`apps.social`). Nenhum contexto novo; entra uma nova **plataforma** e um novo sistema externo (a Evolution do operador) atrás de uma ACL.

## Linguagem ubíqua

| Termo                  | Definição                                                                                              | NÃO confundir com                          |
|------------------------|--------------------------------------------------------------------------------------------------------|--------------------------------------------|
| Instância (Evolution)  | Sessão de um número de WhatsApp pareado na Evolution, identificada por um nome.                         | Número de telefone                         |
| Chave da instância     | Credencial que autoriza enviar pelo número daquela instância; guardada criptografada, nunca exibida.    | Chave global da Evolution (não usada)      |
| Conta de WhatsApp      | `SocialAccount` com `platform=whatsapp_status`; `external_id` = nome da instância.                      | Perfil/Página (têm OAuth e link)           |
| Status do WhatsApp     | Publicação efêmera (≈ 24 h) vista pelos contatos do número; único destino do WhatsApp no Hub.           | Mensagem para contato ou grupo             |
| Estado da conexão      | Se a instância está pareada e ativa (`open`) na Evolution.                                              | Status da conta (`active`/`needs_reauth`)  |
| Reconexão necessária   | (existente) Para o WhatsApp: instância desconectada ou chave recusada; o pareamento é refeito **na Evolution**. | Reconectar via login (OAuth)         |

## Agregados, entidades e value objects
- **Agregado `SocialAccount`** (raiz: `SocialAccount`) — ganha a plataforma `whatsapp_status`.
  - Value objects: `InstanceName` (`^[A-Za-z0-9_-]{1,64}$`), `InstanceKey` (segredo cifrado com Fernet).
  - **Invariantes novas:**
    1. A conta só é **cadastrada** se o estado da conexão for `open` no momento do cadastro.
    2. Uma conta é única por (dono, plataforma, nome da instância); recadastrar a mesma instância **atualiza a chave** (não duplica).
    3. A chave nunca aparece em tela, log, mensagem de erro ou histórico; descriptografada só para enviar.
    4. Instância desconectada ou chave recusada → conta `needs_reauth`; ela **não pode ser marcada** como destino até voltar a `active`.
    5. Não há token com validade: `token_expires_at` é sempre nulo para esta plataforma.
- **Agregado `Publication`** (raiz: `Publication`) — mesmas invariantes de idempotência (claim atômico, `published` imutável, snapshot, status derivado).
  - **Invariantes novas/alteradas:**
    1. O alvo `whatsapp_status` envia **texto sempre** e **imagem se e somente se** a publicação tem imagem (legenda = texto).
    2. A audiência é **todos os contatos** (a privacidade do número manda); não há lista no Hub.
    3. O envio é **uma chamada**: sem container, sem espera, sem retomada; falha → `failed` reenviável.
    4. O alvo publicado **não tem link** (`permalink` vazio); o histórico mostra "link indisponível".
    5. A imagem é lida do arquivo sanitizado e enviada em **base64**; nunca por URL pública.
    6. O host da Evolution vem **só** da configuração do servidor; o usuário informa apenas o nome da instância.
  - Fronteira de consistência: igual à 0004/0005; o estado da conexão é consultado no cadastro e inferido das falhas de envio.

## Eventos de domínio
> Eventos **lógicos** em log (`apps.social.meta`); sem barramento. **Nenhum log traz a chave, o base64 ou o texto.**

| Evento (passado)              | Disparado quando                                              | Quem reage                    |
|-------------------------------|---------------------------------------------------------------|-------------------------------|
| `ContaWhatsAppCadastrada`     | Instância validada (`open`) e gravada com a chave cifrada      | tela, log                     |
| `ContaWhatsAppRemovida`       | O usuário desconecta a conta                                  | histórico preservado, log     |
| `InstanciaDesconectada`       | Estado ≠ `open` ou chave recusada ao enviar/validar           | conta → `needs_reauth`        |
| `StatusEnviado`               | A Evolution confirma o envio do Status                        | alvo → `published`, log       |
| `AlvoPublicado` / `AlvoFalhou`| Resultado do envio (já existentes)                            | histórico, log                |

## Relações com outros contextos
- **Evolution API → Social:** **Anti-Corruption Layer** (`EvolutionClient`): isola o host fixo, a chave por instância e o formato do Status (que varia por versão e **não está confirmado**, ver design).
  É um sistema do operador e **não oficial** (Baileys): o Hub se adapta a ele (Conformist no contrato), mas protege o domínio com a ACL.
- **Publicação → Conta social, Social → Identidade, Social → Painel:** sem mudança.
