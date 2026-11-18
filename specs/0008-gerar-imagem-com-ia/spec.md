---
name: spec
description: Contrato da feature 0008 — gerar imagem com IA (Google Gemini por padrão) na tela de nova publicação, com escolha de modelo, chave de API própria e prompt ao lado. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Gerar imagem com IA na postagem

> Status: implementado (UAT real com chave do Gemini pendente). Os `AC-N` começam em 1.

## Resumo
Na tela **Nova publicação**, uma seção **Criar imagem** (prompt de um lado, resultado do outro) gera uma imagem pelo **Google Gemini** (padrão), com **modelo** escolhível e **chave de API** cadastrável. A imagem gerada passa a ser a imagem da publicação, seguindo os mesmos limites e a mesma sanitização de uma imagem enviada.

## Critérios de aceite

### AC-1: Seção Criar imagem
- **Dado** o formulário de nova publicação
- **Quando** o usuário abre a página
- **Então** há uma seção "Criar imagem" com campo de prompt (lado esquerdo), seletor de modelo (padrão Gemini, primeiro item) e área de pré-visualização (lado direito); em telas estreitas empilha

### AC-2: Gerar
- **Dado** chave cadastrada, modelo escolhido e prompt preenchido
- **Quando** o usuário clica em "Gerar imagem"
- **Então** o Hub chama o Gemini no servidor, sanitiza o resultado (mesma regra de `sanitize_image`) e mostra a pré-visualização; nada é publicado

### AC-3: A imagem gerada é a da publicação
- **Dado** uma imagem gerada e exibida
- **Quando** o usuário publica
- **Então** a publicação usa essa imagem como se tivesse sido enviada (valem as regras de Facebook obrigatório, proporção 10:1 do Threads etc.); se o usuário também escolher um arquivo, **o arquivo escolhido vence** e a UI avisa; "Descartar" remove a imagem gerada

### AC-4: Chave de API por usuário, cifrada
- **Dado** o campo "Chave de API do Gemini"
- **Quando** o usuário a salva
- **Então** ela é guardada cifrada (Fernet, ADR-0002), pertence só a ele, **nunca** é reexibida (só "chave cadastrada · terminada em ••••") nem aparece em log, URL, HTML, JSON ou mensagem de erro; há "Remover chave"; sem chave do usuário usa-se `GEMINI_API_KEY` do servidor, se existir

### AC-5: Sem chave
- **Dado** nem chave do usuário nem do servidor
- **Quando** o usuário tenta gerar
- **Então** recebe a mensagem "Cadastre uma chave de API do Gemini para gerar conteúdo com IA." e nenhuma chamada externa é feita

### AC-6: Erros amigáveis e sanitizados
- **Dado** falha do Gemini (chave inválida, cota, conteúdo bloqueado, timeout, resposta sem imagem)
- **Quando** o usuário gera
- **Então** vê mensagem curta por categoria, sem corpo da resposta, sem chave e sem o prompt em log; o formulário e o texto digitado não se perdem

### AC-7: Isolamento e segurança
- **Dado** usuário A e B
- **Quando** qualquer um gera, salva ou remove chave
- **Então** só atua sobre os próprios dados; endpoints exigem login e CSRF; a imagem gerada só é acessível ao dono; o host do Gemini é fixo no servidor (o usuário nunca informa URL)

### AC-8: Modelos configuráveis
- **Dado** `GEMINI_IMAGE_MODELS` (lista) no servidor
- **Quando** o usuário escolhe um modelo
- **Então** só modelos da lista são aceitos (outro valor é rejeitado); o primeiro é o padrão

### AC-9: Gerar o texto com IA (adicionado após a aprovação do design)
- **Dado** `GEMINI_TEXT_MODEL` configurado (padrão `gemini-2.5-flash`) e uma chave disponível
- **Quando** o usuário escreve um prompt no painel ao lado da caixa de Texto (há "Usar prompt de exemplo") e clica em "Gerar texto"
- **Então** o Hub chama o provedor escolhido (Google Gemini, padrão, ou DeepSeek, via `DEEPSEEK_TEXT_MODEL`) com o modelo de texto padrão dele e preenche a caixa de Texto (editável; pede confirmação antes de substituir texto existente), até o limite geral; a chave é por provedor (cifrada, `AiProviderKey.provider`; cadastro, teste e remoção no próprio painel de texto) e valem as mesmas regras de erro/segurança (AC-4 a AC-7) e nada é publicado; modelo vazio desliga aquele provedor (e o painel, se ambos vazios); provedor desconhecido cai em Gemini

## Casos de borda
- Prompt vazio ou acima de 2000 caracteres → erro de validação, sem chamada.
- Imagem gerada fora dos limites (bytes/pixels) → mesma mensagem de `sanitize_image`.
- Regenerar substitui a imagem gerada anterior.
- Usuário gera mas fecha a página → imagem temporária expira (24 h) e é limpa.

## Fora de escopo
- Outros provedores além de Gemini e DeepSeek (texto) — a arquitetura permite; imagem é só Gemini.
- Editar/variar imagem existente, múltiplas imagens por geração, histórico de prompts, cobrança/cota no Hub.

## Rastreabilidade
- Design: `./design.md` · ADR: a criar (chave de API de terceiros por usuário).
