---
name: spec
description: Contrato da feature 0006 — publicar no Status do WhatsApp (texto e imagem) por uma instância da Evolution API já conectada, como mais um destino do formulário. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — WhatsApp: publicar no Status via Evolution API

> **Fonte da verdade.** Status: implementado (UAT real em 2026-11-17 na Evolution 2.3.7)
> Os critérios de aceite são (a) o contrato com o negócio, (b) o oráculo de teste,
> (c) o prompt para o agente de IA implementar. Os `AC-N` desta spec são numerados a partir de 1 (independentes das anteriores).
> **Contrato confirmado no UAT (Evolution 2.3.7):** corpo plano em `POST /message/sendStatus/{instância}`; texto exige `backgroundColor` e `font`; imagem vai como **data URI** (base64 puro é lido como caminho de arquivo). Esta spec descreve **comportamento**; o corpo fica isolado em `EvolutionClient`.

## Resumo
O Hub passa a aceitar uma **instância da Evolution já pareada** como conta de WhatsApp (nome da instância + chave, cifrada; host só do servidor) e a publicar o **Status do WhatsApp**
(texto, ou imagem em base64 com o texto como legenda) para **todos os contatos**, como mais um destino do formulário, ao lado de Facebook e Threads, com resultado por destino, falha reenviável e idempotência.

## Critérios de aceite
> Cada `AC-N` reaparece em `tasks.md` (coluna "Cobre AC"), no teste que o valida e no commit.

### AC-1: Cadastrar uma instância
- **Dado** a Evolution configurada no servidor e um usuário logado
- **Quando** ele informa um nome de instância válido e a chave dela, e a Evolution responde que a instância está `open`
- **Então** é criada uma conta `whatsapp_status` **ativa** do usuário (`external_id` = nome da instância) com a chave **cifrada**, o usuário vê mensagem de sucesso e a chave **não** é exibida nem ecoada em lugar nenhum

### AC-2: Cadastro recusado
- **Dado** o formulário de cadastro
- **Quando** o nome é inválido, a instância não está `open`, a chave é recusada, a instância não existe ou a Evolution está inacessível (matriz de cadastro)
- **Então** **nada é gravado**, aparece uma mensagem amigável específica do caso (nunca o texto cru da Evolution) e a chave digitada não é devolvida na página

### AC-3: Recadastrar a mesma instância
- **Dado** uma conta de WhatsApp já cadastrada (inclusive em Reconexão necessária)
- **Quando** o mesmo usuário cadastra de novo o mesmo nome de instância com uma chave válida
- **Então** a conta existente é **atualizada** (nova chave cifrada, status `active`, erro limpo), sem duplicar

### AC-4: Integração não configurada
- **Dado** `EVOLUTION_API_URL` vazio ou que não seja HTTPS
- **Quando** o usuário abre Contas ou tenta cadastrar/publicar
- **Então** a tela mostra "Integração com o WhatsApp não configurada" e o cadastro é indisponível (POST rejeitado, nada gravado); contas de WhatsApp já existentes ficam **desabilitadas** no formulário de publicação; Facebook e Threads seguem normais

### AC-5: Listar, verificar e desconectar
- **Dado** contas de WhatsApp do usuário
- **Quando** ele abre Contas, usa "Verificar" ou "Desconectar"
- **Então** a lista mostra a plataforma, o nome da instância e o status (sem a chave); "Verificar" consulta o estado da conexão e atualiza a conta (`open` → ativa; senão Reconexão necessária); "Desconectar" remove a conta e **preserva** o histórico das publicações (alvo mantém o nome, sem conta)

### AC-6: Destinos do WhatsApp no formulário
- **Dado** o formulário de nova publicação
- **Quando** é aberto
- **Então** as contas de WhatsApp ativas aparecem num grupo "Status do WhatsApp", com "Marcar todas" por grupo e a explicação das regras; contas em Reconexão necessária aparecem **desabilitadas** com aviso e orientação ("reconecte o número na Evolution"); contas de outros usuários nunca aparecem

### AC-7: Regras do formulário com WhatsApp
- **Dado** um envio do formulário com destinos marcados
- **Quando** o WhatsApp está entre eles (matriz do formulário)
- **Então** a **imagem é opcional** se não há Página do Facebook (e continua obrigatória com ela); uma imagem enviada é sempre validada e sanitizada como na 0003; o texto vazio é inválido; o limite de texto do WhatsApp **não é validado** além do limite geral já existente (não documentado); seleção inválida (conta de outro usuário, em reconexão, inexistente ou integração não configurada) é rejeitada e **nada é criado**

### AC-8: Publicar Status de texto
- **Dado** uma publicação **sem imagem** com um alvo `whatsapp_status` reivindicado
- **Quando** o envio ocorre
- **Então** a Evolution recebe **uma** chamada de Status de **texto** para a instância da conta, com a chave dela, o texto da publicação e a audiência **todos os contatos**; o alvo vira `published` (id da mensagem guardado quando houver, `permalink` vazio) e é logado `evolution_status_sent`

### AC-9: Publicar Status de imagem
- **Dado** uma publicação **com imagem** e um alvo `whatsapp_status` reivindicado
- **Quando** o envio ocorre
- **Então** a Evolution recebe **uma** chamada de Status de **imagem** com o arquivo sanitizado em **base64** (nunca por URL pública), o texto como **legenda** e a audiência **todos os contatos**; imagem ausente do disco → alvo `failed` com a mensagem de imagem indisponível e **nenhuma** chamada à Evolution

### AC-10: Destinos mistos independentes
- **Dado** uma publicação com Facebook, Threads e WhatsApp marcados
- **Quando** o envio ocorre
- **Então** cada alvo é despachado à sua plataforma e tem resultado próprio; a falha de um **não impede** os outros; o status geral continua derivado dos alvos; "Tentar novamente" reenvia só `failed`/`pending`, nunca `published`

### AC-11: Instância desconectada ou chave recusada ao publicar
- **Dado** um alvo do WhatsApp
- **Quando** a conta já está em Reconexão necessária, ou a Evolution responde autenticação recusada / instância inexistente / estado diferente de `open` (matriz de envio)
- **Então** o alvo fica `failed` com "Reconecte o número na Evolution", a conta passa a **Reconexão necessária** (sem chamar a Evolution quando já estava) e o reenvio só funciona depois de a conta voltar a `active`

### AC-12: Outras falhas são reenviáveis
> **Atualizado pela [0007](../0007-publicacao-em-segundo-plano/spec.md):** o **tempo esgotado** (e a conexão cortada depois de enviar) do `sendStatus` agora leva o alvo ao estado **Incerto** ("Não foi possível confirmar se foi publicado…"), com "Já foi publicado" ou "Reenviar"; a mensagem específica de timeout desta spec foi substituída (nos dois modos, `worker` e `inline`). Os demais erros seguem como aqui.
- **Dado** um alvo do WhatsApp
- **Quando** a Evolution falha por tempo esgotado, erro de rede, erro 5xx, limite de requisições ou recusa do conteúdo (matriz de envio)
- **Então** o alvo fica `failed` com mensagem **amigável** do caso (nunca o texto cru da Evolution) e código curto, a conta **não** muda de status e "Tentar novamente" o reenvia; no **tempo esgotado** a mensagem avisa que o **Status pode ter sido publicado** e manda conferir no celular antes de tentar de novo (UAT: com ~2265 contatos a Evolution concluiu depois de o Hub desistir)

### AC-13: Orçamento de tempo
> **Atualizado pela [0007](../0007-publicacao-em-segundo-plano/spec.md):** o `min(EVOLUTION_TIMEOUT_SECONDS, orçamento restante − 25 s)` e o limite de 40 s valem só no modo `inline`; o **worker** usa `EVOLUTION_TIMEOUT_SECONDS` inteiro.
- **Dado** a requisição de envio com orçamento (ADR-0009)
- **Quando** há alvo do WhatsApp
- **Então** o tempo limite da chamada é `min(EVOLUTION_TIMEOUT_SECONDS, orçamento restante − 25 s)`; com menos de 40 s restantes o alvo **não é iniciado** e continua `pending`

### AC-14: Segurança — segredos e destino
- **Dado** qualquer fluxo desta feature
- **Quando** cadastrar, verificar, publicar, falhar ou renderizar telas
- **Então** a chave, o base64 e o texto **não** aparecem em logs, HTML, mensagens, exceções nem no histórico; o host da chamada é **sempre** o do servidor (o usuário só informa o nome da instância, validado e codificado na rota — `/`, `..`, `?`, `#`, espaço e similares são rejeitados); o formulário de cadastro não reexibe a chave

### AC-15: Histórico e detalhe
- **Dado** uma publicação com alvo `whatsapp_status`
- **Quando** o usuário abre o detalhe ou o histórico
- **Então** o alvo aparece como "Status do WhatsApp" com o nome da instância e o estado; publicado **sem link** mostra "link indisponível"; uma publicação **só de texto** continua mostrando o ícone no lugar da imagem

### AC-16: Isolamento entre usuários
- **Dado** contas de WhatsApp de usuários diferentes (inclusive com o mesmo nome de instância)
- **Quando** um usuário lista, verifica, desconecta ou marca destinos
- **Então** só enxerga e opera as **próprias** contas; operar a conta de outro → 404; publicar com conta de outro é rejeitado

### AC-17: Documentação e configuração
- **Dado** o repositório
- **Quando** se consulta `.env.example` e o README
- **Então** `EVOLUTION_API_URL` e `EVOLUTION_TIMEOUT_SECONDS` estão documentados, com o aviso de que o Baileys **não é oficial** e há risco de banimento, e a orientação de usar a chave **da instância** (nunca a global)

## Matriz de decisão

### Cadastro da instância (AC-1, AC-2, AC-3)
| Nome da instância | Estado/resposta da Evolution | Resultado | AC |
|---|---|---|---|
| válido | `open` | conta `active` criada, chave cifrada | AC-1 |
| válido, já cadastrada | `open` | conta atualizada (chave nova, `active`), sem duplicar | AC-3 |
| válido | estado ≠ `open` (`close`, `connecting`) | recusa: "O número não está conectado na Evolution" | AC-2 |
| válido | 401/403 (chave recusada) | recusa: "Chave recusada pela Evolution" | AC-2 |
| válido | 404 (instância inexistente) | recusa: "Instância não encontrada" | AC-2 |
| válido | timeout / rede / 5xx | recusa: "Não foi possível falar com a Evolution" | AC-2 |
| vazio, > 64 caracteres ou com `/ . ? # %` ou espaço | — (nenhuma chamada) | recusa de formulário | AC-2 |
| qualquer | `EVOLUTION_API_URL` ausente ou não HTTPS | indisponível; nada gravado | AC-4 |

### Formulário de publicação (AC-6, AC-7)
| Facebook | Threads | WhatsApp | Imagem | Resultado | AC |
|---|---|---|---|---|---|
| — | — | marcado | ausente | criada sem imagem | AC-7 |
| — | — | marcado | válida | criada com imagem | AC-7 |
| — | — | marcado | inválida | rejeitada (erro da imagem) | AC-7 |
| marcado | — | marcado | ausente | rejeitada ("Escolha uma imagem") | AC-7 |
| marcado | marcado | marcado | válida | cria os 3 alvos | AC-7 |
| — | marcado | marcado | ausente | criada; regras do Threads (500, 5 links) também valem | AC-7 |
| — | — | marcado | texto vazio | rejeitada | AC-7 |
| — | — | conta de outro usuário / em reconexão / inexistente | — | rejeitada, nada criado | AC-7 |

### Envio ao WhatsApp (AC-8, AC-9, AC-11, AC-12)
| Situação | Alvo | Conta | Mensagem | AC |
|---|---|---|---|---|
| sucesso, sem imagem | `published` (texto) | igual | — | AC-8 |
| sucesso, com imagem | `published` (imagem + legenda) | igual | — | AC-9 |
| arquivo da imagem ausente | `failed` | igual | imagem indisponível | AC-9 |
| conta já em Reconexão necessária | `failed` (sem chamada) | igual | "Reconecte o número na Evolution" | AC-11 |
| 401/403 | `failed` | → `needs_reauth` | "Reconecte o número na Evolution" | AC-11 |
| 404 (instância inexistente) | `failed` | → `needs_reauth` | "Reconecte o número na Evolution" | AC-11 |
| estado ≠ `open` | `failed` | → `needs_reauth` | "Reconecte o número na Evolution" | AC-11 |
| timeout (sem resposta no prazo) | `failed` | igual | "A Evolution demorou a responder. O Status pode ter sido publicado: confira no celular antes de tentar novamente." | AC-12 |
| rede / 5xx / resposta inválida | `failed` | igual | "Falha de comunicação com a Evolution" | AC-12 |
| 429 | `failed` | igual | "Limite de requisições. Tente mais tarde." | AC-12 |
| 400 / recusa de conteúdo | `failed` | igual | "A Evolution recusou este conteúdo" | AC-12 |
| < 40 s de orçamento | `pending` (não iniciado) | igual | — | AC-13 |

## Casos de borda e erros
- **Timeout depois de a Evolution já ter enviado:** o alvo falha e um reenvio **duplica** o Status (janela conhecida, [issue #1](https://github.com/thalisonwilker/social-hub/issues/1)); **observado no UAT** (audiência de ~2265 contatos, envio > 60 s). Mitigação: `EVOLUTION_TIMEOUT_SECONDS` padrão 120 e a mensagem de timeout que manda conferir no celular; idempotência real fica para a fila.
- **Chave com espaços/quebras de linha ao colar:** removidos antes de validar; chave vazia é rejeitada.
- **Resposta sem id da mensagem:** o alvo ainda vira `published` (o id é opcional); sem link.
- **Resposta não-JSON ou fora do formato esperado:** `failed` com "Falha de comunicação com a Evolution"; o corpo cru nunca é logado.
- **Imagem grande:** o corpo em base64 é ~33% maior; respeita o orçamento de tempo (AC-13).
- **Duplo clique/duas requisições:** o claim atômico existente garante um envio por alvo.
- **Conta desconectada com publicações antigas:** o histórico permanece (alvo sem conta, não reenviável).

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Pareamento por QR code, criação/exclusão de instâncias e qualquer gestão da Evolution além de ler o estado da conexão.
- Mensagens para contatos, grupos ou canais; lista de contatos/JIDs; cor/fonte do fundo do Status de texto; vídeo, áudio, figurinha, enquete.
- WhatsApp Cloud API oficial; webhooks da Evolution; fila/worker; agendamento; apagar ou editar Status; link para o Status.
- Validar o limite de caracteres do Status (não documentado); mudar Facebook ou Threads.
- Uso da chave **global** da Evolution.

## Rastreabilidade
- Product: [`./product.md`](./product.md)
- Design: [`./design.md`](./design.md)
- Domínio: [`./domain.md`](./domain.md)
- ADRs relacionados: [0002](../../docs/architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md) · [0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md) · [0009](../../docs/architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md) · [0010](../../docs/architecture/adr/0010-whatsapp-status-via-evolution-api-instancia-chave-cifrada-e-host-fixo.md) (credenciais por instância, host fixo, Baileys)
- Specs afetadas: [0003](../0003-publicar-no-facebook/spec.md) (destinos do formulário) e [0004](../0004-threads-conectar-e-publicar/spec.md) (regras de imagem/seleção) ganham nota de que o WhatsApp também é destino.
