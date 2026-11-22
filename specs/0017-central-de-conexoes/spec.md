---
name: spec
description: Contrato da feature 0017 — central de conexões em /contas/ (coluna de ícones Facebook/Instagram/Threads/WhatsApp como navegação + painel de detalhes da rede selecionada, troca sem recarregar, seguidores buscados na API ao "Atualizar informações", ações conectar/atualizar/reconectar/desconectar reaproveitadas). Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Central de conexões

> **Fonte da verdade.** Status: aprovado · implementado (UAT no navegador feito com dados fictícios; falta o UAT com contas reais)
> Tier: **pequeno** (redesenho da tela `Contas conectadas` reaproveitando as ações existentes; o único
> dado novo é `followers_count`, lido pelos clientes Graph/Threads que já existem). `AC-N` começam em 1.
> Referência visual: "Conceito 03 — Ícones + painel de detalhes" (imagem anexada à abertura da feature).

## Resumo
A página `/contas/` (`social:accounts`) vira uma central de conexões em duas colunas: à esquerda, só os
ícones das quatro redes (Facebook, Instagram, Threads, WhatsApp) servindo de navegação; à direita, um
painel com os dados e as ações da rede selecionada — troca instantânea, sem recarregar a página.

## Termos
- **Rede**: um dos quatro canais da coluna de ícones. Mapeia para `SocialAccount.Platform`:
  Facebook = `facebook_page`, Instagram = `instagram`, Threads = `threads`, WhatsApp = `whatsapp_status`.
- **Rede conectada**: existe ≥ 1 `SocialAccount` dessa plataforma no escopo do perfil ativo
  (`profiles.scope`, como hoje). **Desconectada**: nenhuma.
- **Conta em destaque**: a conta da rede exibida no painel (a primeira por `name`, ou a escolhida no seletor).

## Critérios de aceite

### AC-1: Layout em duas colunas
- **Dado** um usuário logado com perfil ativo
- **Quando** abre `/contas/` numa largura ≥ 768 px
- **Então** vê, lado a lado, (a) uma coluna estreita só com os 4 ícones, empilhados verticalmente e
  centralizados, na ordem Facebook, Instagram, Threads, WhatsApp, cada um num botão quadrado de cantos
  arredondados, fundo discreto e espaçamento uniforme; e (b) um painel maior com bordas sutis à direita.
  A coluna de ícones não contém textos além dos rótulos acessíveis/tooltip.

### AC-2: Estado visual de cada ícone
- **Dado** a coluna de ícones
- **Quando** a página é renderizada
- **Então** cada ícone segue a Matriz de decisão (cor do ícone + indicador) e o ícone da rede selecionada
  tem destaque laranja (borda ou fundo, token `accent`), visível em conjunto com o indicador.

### AC-3: Hover e tooltip
- **Dado** um ícone da coluna
- **Quando** o ponteiro passa sobre ele ou ele recebe foco do teclado
- **Então** há um efeito suave de iluminação e um tooltip com o nome da rede ("Facebook", "Instagram",
  "Threads", "WhatsApp").

### AC-4: Seleção inicial
- **Dado** que o usuário abre `/contas/` sem parâmetro
- **Quando** a página carrega
- **Então** a rede selecionada é a primeira **conectada** na ordem da coluna; se nenhuma estiver
  conectada, é o Facebook.
- **E** com `/contas/?rede=<facebook|instagram|threads|whatsapp>` a rede indicada vem selecionada;
  valor desconhecido é ignorado (cai na regra acima), sem erro.

### AC-5: Troca de rede sem recarregar
- **Dado** a página carregada com JavaScript
- **Quando** o usuário clica num ícone (ou o ativa pelo teclado)
- **Então** o painel passa a mostrar a rede escolhida **sem nova requisição de página**, com transição
  suave (fade ≤ 200 ms; nenhuma animação com `prefers-reduced-motion: reduce`), o destaque laranja muda
  de ícone e a URL é atualizada para `?rede=<rede>` sem entrada nova no histórico.
- **E** sem JavaScript, cada ícone é um link para `?rede=<rede>` e a página renderizada no servidor
  mostra o painel correspondente (progressive enhancement, como na spec 0012).

### AC-6: Painel de rede conectada
- **Dado** que a rede selecionada está conectada
- **Quando** o painel é exibido
- **Então** mostra, para a conta em destaque:
  1. **Cabeçalho**: avatar (`picture_url` ou ícone da rede), nome da conta e status da conexão
     ("Conexão ativa" em verde, ou "Reconexão necessária" em âmbar).
  2. **Informações** (em pares rótulo/valor, sem tabela): **Usuário** (`@username`; Facebook: categoria;
     Instagram: "via Página <nome>"; WhatsApp: "instância <external_id>"), **Seguidores**
     (`followers_count` formatado pt-BR, ou "—" se nulo), **Publicações** (nº de alvos de publicação
     `published` dessa conta no Hub) e **Conectada em** (`connected_at`, dd/mm/aaaa).
  3. **Última sincronização** (`last_checked_at`, dd/mm/aaaa hh:mm, ou "Nunca") e **Permissões**
     concedidas (`granted_tasks` como chips; lista vazia → "—").
  4. **Ações**: "Atualizar informações", "Reconectar" e "Desconectar" (AC-9, AC-10, AC-11).
  Nenhum token ou chave aparece no HTML.

### AC-7: Várias contas na mesma rede
- **Dado** que a rede selecionada tem 2+ contas no perfil ativo
- **Quando** o painel é exibido
- **Então** acima do cabeçalho há uma lista compacta (abas/seletor) com o nome de cada conta; a primeira
  por `name` vem em destaque e escolher outra troca o conteúdo do painel sem recarregar (mesma regra de
  transição do AC-5). Com 1 conta, a lista não aparece.

### AC-8: Painel de rede desconectada
- **Dado** que a rede selecionada está desconectada
- **Quando** o painel é exibido
- **Então** mostra o ícone da rede em destaque, a mensagem "Nenhuma conta vinculada" com uma linha curta
  de apoio, e um botão laranja **"Conectar conta"** que dispara o fluxo atual da rede:
  Facebook → POST `social:facebook_connect`; Instagram → POST `social:facebook_connect` (o Instagram vem
  pela Página — a linha de apoio diz "O Instagram é conectado pela sua Página do Facebook.");
  Threads → POST `social:threads_connect`; WhatsApp → GET `social:whatsapp_new`.
- **E** se a integração da rede não estiver configurada (`meta_configured` / `threads_configured` /
  `evolution_configured`), o botão fica desabilitado e a linha de apoio diz "Integração com a Meta não
  configurada" (Facebook/Instagram), "Integração com o Threads não configurada" ou "Integração com o
  WhatsApp não configurada". *(Ajustado na implementação para manter as mensagens das specs 0004 e 0006.)*

### AC-9: Atualizar informações (inclui seguidores)
- **Dado** uma conta conectada
- **Quando** o usuário clica em "Atualizar informações"
- **Então** o Hub executa a verificação atual (`social:account_check`, mesmas regras de status e
  mensagens) e, na mesma ida, lê o número de seguidores na plataforma e grava em `followers_count`;
  `last_checked_at` é atualizado e o usuário volta a `/contas/?rede=<rede>` com a mesma rede selecionada.
- **E** se a leitura de seguidores falhar sem erro de token, o status da conta não muda e o
  `followers_count` anterior é mantido (a verificação em si segue as regras atuais).
- **E** WhatsApp não tem seguidores e o Threads não é consultado (exigiria `threads_manage_insights`):
  nos dois, `followers_count` fica nulo e o painel mostra "—".

### AC-10: Reconectar
- **Dado** uma conta conectada (ativa ou com reconexão necessária)
- **Quando** o usuário clica em "Reconectar"
- **Então** dispara o mesmo fluxo de conexão do AC-8 para a rede (WhatsApp: `social:whatsapp_new?instance=<external_id>`);
  desabilitado com a mesma mensagem do AC-8 se a integração não estiver configurada.
  Com status "Reconexão necessária", "Reconectar" é o botão primário (laranja); com status ativo, é secundário.

### AC-11: Desconectar
- **Dado** uma conta conectada
- **Quando** o usuário clica em "Desconectar"
- **Então** vale o comportamento atual de `social:account_disconnect`, inclusive o diálogo de confirmação
  com o texto atual (Página do Facebook avisa que o Instagram vinculado também sai); depois o usuário
  volta a `/contas/?rede=<rede>`.

### AC-12: Responsivo (celular)
- **Dado** uma largura < 768 px
- **Quando** a página é exibida
- **Então** os 4 ícones ficam numa linha, centralizados horizontalmente, **acima** do painel; o painel
  ocupa a largura toda; não há rolagem horizontal; os botões de ação ficam empilhados ou em linha sem cortar texto.

### AC-13: Acessibilidade
- **Dado** a coluna de ícones
- **Então** ela é um `tablist` (rótulo "Redes sociais"), cada ícone é um `tab` com nome acessível
  "<Rede> — conectada|desconectada|reconexão necessária", `aria-selected` na rede atual, setas
  movem o foco entre ícones e Enter/Espaço selecionam; o painel é o `tabpanel` ligado por `aria-controls`.
  O indicador de status nunca depende só da cor (o nome acessível e o texto do cabeçalho o repetem).

### AC-14: Tema
- **Dado** o tema escuro (referência visual)
- **Então** a tela segue a estética da imagem (fundo escuro, bordas sutis, espaçamento generoso,
  laranja como destaque) usando os tokens de cor existentes; **e** no tema claro a tela continua
  legível e com o mesmo layout (sem cores fixas fora dos tokens).

## Matriz de decisão — ícone da rede (AC-2)

| Contas da rede no perfil | Status das contas | Ícone | Indicador | Nome acessível | AC |
|---|---|---|---|---|---|
| 0 | — | acinzentado | neutro (cinza) | "<Rede> — desconectada" | AC-2, AC-13 |
| ≥ 1 | todas `active` | colorido (cor da marca) | verde | "<Rede> — conectada" | AC-2, AC-13 |
| ≥ 1 | alguma `needs_reauth` | colorido | âmbar | "<Rede> — reconexão necessária" | AC-2, AC-13 |

A seleção (destaque laranja) é independente e combina com qualquer linha.

## Matriz de decisão — botão primário do painel

| Rede conectada | Status da conta em destaque | Integração configurada | Botão primário (laranja) | AC |
|---|---|---|---|---|
| não | — | sim | "Conectar conta" habilitado | AC-8 |
| não | — | não | "Conectar conta" desabilitado + mensagem da rede (AC-8) | AC-8 |
| sim | `active` | — | "Atualizar informações" | AC-9 |
| sim | `needs_reauth` | sim | "Reconectar" | AC-10 |
| sim | `needs_reauth` | não | "Reconectar" desabilitado + mensagem da rede (AC-8) | AC-10 |

## Casos de borda e erros
- `?rede=` com valor inválido ou vazio → ignora e aplica a seleção inicial (AC-4); nunca 4xx/5xx.
- Conta de outro usuário em `account_check`/`account_disconnect` → 404 (comportamento atual, mantido).
- Instagram cuja Página foi removida não existe (cascata atual); Instagram sem Página não aparece.
- Falha de rede/timeout ao ler seguidores → mantém o valor anterior, sem mudar status (AC-9).
- Avatar que não carrega (URL expirada da Meta) → cai no ícone da rede (sem imagem quebrada).
- Perfil sem nenhuma conta → Facebook selecionado, painel desconectado (AC-4 + AC-8).

## Pontos a confirmar — resultado da task 0 (doc oficial Meta, 2026-11-21)
- **Facebook (Página)**: campo `followers_count` do nó Page ("Number of page followers"). O `fan_count`
  conta curtidas e, em Páginas da Nova Experiência, devolve o próprio `followers_count`, então usamos
  `followers_count`. As permissões `pages_read_engagement` e `pages_show_list` já estão no `config_id` (README). Fonte:
  developers.facebook.com/docs/graph-api/reference/page/
- **Instagram (IG User)**: campo `followers_count` ("Total number of Instagram users following the user").
  Pelo Login do Facebook, exige `instagram_basic` + `pages_read_engagement`, que já são pedidas (spec 0009).
  A doc fala em token de usuário. O Hub usa o token da Página, como na publicação (ADR-0013): **a confirmar
  no UAT**. Se recusar sem erro de token, vale a regra do AC-9 (mantém o valor e mostra "—"). Fonte:
  developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/
- **Threads**: não há campo de seguidores no `/me`. O caminho é `GET /{threads-user-id}/threads_insights?metric=followers_count`,
  que exige **`threads_manage_insights`**, permissão que o app **não pede** hoje (`threads.SCOPES`).
  O `profile_lookup` (`follower_count`) exige `threads_profile_discovery` e não serve para o próprio perfil.
  Fonte: developers.facebook.com/docs/threads/insights/ · /docs/threads/threads-profiles/
  **Decidido (2026-11-21)**: o Threads mostra "—" nesta feature, sem permissão nova (ver AC-9 e "Fora de escopo").

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Novas redes (Twitter/X, TikTok) ou ícones "Em breve" nesta tela.
- Sincronização automática/em segundo plano de seguidores; histórico ou gráfico de seguidores.
- Seguidores do Threads (exige a permissão `threads_manage_insights`, que pede reconexão; fica para uma feature futura).
- Número de publicações lido da plataforma (o painel conta só o que o Hub publicou).
- Mudanças no wizard de perfil (`profiles/wizard_connect.html`), no shell/menu lateral ou nos fluxos
  OAuth/Evolution em si.
- Forçar tema escuro; novos tokens de cor fora do sistema da spec 0012.
- Renomear/excluir perfil; mover contas entre perfis.

## Notas de implementação
- O cabeçalho da conta também mostra a plataforma ("· Página do Facebook") e, no Threads, a validade do
  token: mantêm os critérios AC-9 da spec 0004 e AC-5 da spec 0006, que valiam para a tela antiga.
- Cores de marca dos ícones ficam em variáveis `--brand` (`frontend/input.css`). O tema continua só nos tokens.
- Testes antigos que conferiam textos da tela anterior ("Conectar Facebook", "Ativa", "Nenhuma conta
  conectada", redirect para `/contas/`) foram atualizados para este contrato.

## Rastreabilidade
- Tela atual: `templates/social/accounts.html`, `apps/social/views.py` (`AccountsView`, `AccountCheckView`)
- Interface MUI por ilhas: `specs/0012-interface-mui/` (ADR-0015)
- Instagram via Página: ADR-0013 · Threads: ADR-0006 · WhatsApp: ADR-0010
