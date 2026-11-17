---
name: product
description: PRD-lite da feature 0005 — publicar imagem + texto no Threads, com URL pública temporária e assinada servida pelo Hub.
alwaysApply: false
---

# Product — Threads: publicar imagem junto com o texto

> **Tier:** arquitetural · **Status:** aprovado · **Dono:** Thalyson
> Responde: **por quê** e **para quem**. Depende da [0004](../0004-threads-conectar-e-publicar/spec.md) (Threads), da [0003](../0003-publicar-no-facebook/spec.md) (publicação e imagens) e do [ADR-0005](../../docs/architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md).

## Problema
Hoje um post misto (Facebook + Threads) sai com a imagem **só no Facebook**; no Threads vai apenas o texto (non-goal da 0004). O
usuário que publica "uma vez e escolhe os destinos" precisa abrir o Threads e repetir o post com a imagem. O motivo técnico: a Threads API
**busca a imagem numa URL pública** ("must be on a public server"), e as imagens do Hub são privadas, entregues só por uma rota autenticada (ADR-0005).

## Para quem
Usuários do Social Hub com perfil do Threads conectado que publicam conteúdo com imagem. Uso recorrente, junto com as Páginas do Facebook.

## Resultado esperado / métrica de sucesso
Uma publicação com imagem chega ao Threads com **texto + imagem**, no mesmo clique, sem o usuário abrir o Threads.
- Métrica: tempo para publicar texto + imagem em Facebook e Threads.
- Baseline: texto no Threads, imagem manual (≈ 1–2 min a mais) → Alvo: ≤ 1 min no total, tudo pelo Hub.

## Goals
- **Sempre que a publicação tiver imagem, o Threads recebe texto + imagem** (misto ou só Threads); sem imagem, continua só texto.
- **URL pública temporária e assinada**, servida pelo Hub: token assinado com **validade curta**, que dá acesso **somente à imagem já sanitizada**
  daquela publicação; nenhuma listagem, nenhum acesso ao resto do Hub. Substitui, para o Threads, a regra "sem URL pública" do ADR-0005 (novo ADR).
- **Endereço público configurável** (`PUBLIC_BASE_URL`, HTTPS): a URL entregue à Meta nunca é montada a partir do cabeçalho `Host` da requisição.
- Container `IMAGE` do Threads com **espera adequada ao processamento da mídia** (maior que a do texto), reaproveitando a retomada pelo `external_container_id`.
- **Validação para o Threads** no formulário, só do que a documentação afirma: JPEG/PNG, até 8 MB (já garantidos) e **proporção até 10:1**.
- **Falha explícita:** se a Meta não conseguir buscar ou processar a imagem, o alvo **falha com mensagem amigável** e pode ser reenviado; **sem** degradar para texto às escondidas.
- Funciona em **desenvolvimento via túnel HTTPS** e em **produção via domínio com TLS**; sem `PUBLIC_BASE_URL` configurado, a imagem para o Threads fica indisponível com aviso claro.

## Non-goals
- Várias imagens (carrossel), vídeo, GIF, texto alternativo (`alt_text`: não consta na documentação lida).
- Armazenamento externo (S3/R2) — descartado nesta etapa.
- Mudar o comportamento do Facebook (continua upload direto) ou a regra "imagem obrigatória com Página do Facebook".
- URLs públicas permanentes ou galeria pública de imagens.
- Imagem no Instagram; agendamento; renovação de token em segundo plano; callbacks de desinstalação/exclusão.
- Opção por publicação para "não enviar a imagem ao Threads" (decisão: a imagem vai sempre que existir).

## Impacto em specs e ADRs existentes
- **0004:** os critérios que dizem que o Threads **ignora a imagem** e envia só texto (AC-14, AC-17, AC-21 e o non-goal de imagem) passam a ser **atualizados** por esta feature.
- **ADR-0005:** continua valendo para o Facebook e para a visualização do dono; um **novo ADR** registra a exceção (URL assinada temporária só para a Meta buscar a imagem).
- **0003:** sem mudança.

## Riscos / premissas
- **Premissa:** o app Meta já tem o caso de uso do Threads e o perfil de teste conectado (0004).
- **Risco (segurança):** um endpoint **público** serve uma imagem do usuário. Mitigação a detalhar no design: token assinado imprevisível, validade curta, escopo mínimo (uma imagem),
  sem listagem, sem dependência do `Host`, resposta sem cache público, logs sem o token.
- **Risco:** a Meta precisa **alcançar** o Hub. Túnel fora do ar, firewall ou domínio sem TLS fazem o container falhar → falha reenviável com mensagem clara.
- **Risco:** a documentação **não informa** se HTTPS é obrigatório, se há redirecionamentos, o user-agent do buscador nem o tempo limite → servir a imagem **direto** (sem redirecionar), sempre por HTTPS, e validar no UAT.
- **Risco:** não há códigos de erro de imagem documentados (só os de vídeo) → mapeamento genérico e ajuste após o UAT.
- **Risco:** o processamento de imagem pode passar do orçamento de espera da requisição síncrona → o fluxo já trata como falha reenviável com retomada do mesmo container.
- **Risco:** a proporção "10:1" não diz se é mínimo, máximo ou ambos → validação conservadora nos dois sentidos.
- **Risco:** URLs assinadas vazadas valem só durante a validade curta; aceito e documentado.
