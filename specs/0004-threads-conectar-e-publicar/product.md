---
name: product
description: PRD-lite da feature 0004 — conectar um perfil do Threads e publicar texto, junto com as Páginas do Facebook.
alwaysApply: false
---

# Product — Threads: conectar perfil e publicar texto

> **Tier:** arquitetural · **Status:** aprovado · **Dono:** Thalyson
> Responde: **por quê** e **para quem**. Depende da [0002](../0002-facebook-page-connect/spec.md) (contas) e da [0003](../0003-publicar-no-facebook/spec.md) (publicação).

## Problema
O Social Hub publica só no Facebook. Quem também mantém um perfil no Threads precisa abrir o Threads e repetir o texto à mão,
perdendo o ganho de "publicar uma vez e escolher onde". O Threads tem **login e tokens próprios** (separados do Facebook),
o que exige um fluxo de conexão novo; e os tokens **expiram** (60 dias), algo que o Hub ainda não trata.

## Para quem
Usuários do Social Hub que têm um perfil **público** do Threads (inicialmente o dono do projeto, como testador do app Meta).
Uso recorrente: publicar o mesmo conteúdo em Facebook e Threads, ou só no Threads.

## Resultado esperado / métrica de sucesso
O usuário conecta o perfil do Threads, e na mesma tela de nova publicação marca Páginas do Facebook e/ou perfis do Threads,
publica e vê o resultado por destino.
- Métrica: tempo para publicar um texto em um perfil do Threads e uma Página do Facebook.
- Baseline: manual em dois apps (≈ 1–2 min cada) → Alvo: ≤ 1 min no total, a partir do Hub.

## Goals
- **Conectar o perfil do Threads** com o login próprio do Threads (permissões `threads_basic` e `threads_content_publish`),
  guardando o token de longa duração **criptografado**, com a **data de expiração**.
- *Contas conectadas* mostra os perfis do Threads (usuário, status, validade do token) com **Verificar**, **Desconectar** e **Reconectar**.
- **Renovação do token sob demanda**: ao publicar ou ao **Verificar**, renova se faltar pouco para vencer; se já venceu, a conta
  vira "Reconexão necessária". *Contas conectadas* só **sinaliza** a validade (sem chamada à rede).
- **Publicar texto no Threads (até 500 caracteres)** pelo **mesmo formulário** da 0003, com **alvos mistos** (Páginas do Facebook +
  perfis do Threads), resultado por destino, tentar de novo só os que falharam e sem duplicar.
- Regras do formulário por destino: **imagem obrigatória apenas se houver Página do Facebook marcada**; limite de 500 caracteres
  apenas se houver perfil do Threads marcado.
- A dashboard marca o Threads como "Conectado" quando houver perfil ativo.

## Non-goals
- Imagem, vídeo e carrossel no Threads (dependem de URL pública; feature futura).
- Respostas, menções, insights e demais recursos da Threads API.
- Instagram.
- Agendamento e fila; renovação de token em segundo plano.
- Perfis privados do Threads.
- Tratar de fato os callbacks de desinstalação e exclusão de dados (ficam vazios no app Meta nesta etapa).
- Publicação de **só texto no Facebook** (continua exigindo imagem quando há Página do Facebook).

## Impacto em specs existentes
- **0003:** a regra "imagem obrigatória" passa a valer só quando há Página do Facebook entre os destinos; publicação **somente no
  Threads** não exige imagem. Os critérios afetados serão **atualizados na spec 0003** (e seus testes) ao aprovar esta feature.
- **0002:** o modelo `SocialAccount` ganha a plataforma `threads` e uma data de expiração do token.

## Riscos / premissas
- **Premissa:** o caso de uso *Acessar a API do Threads* está no app Meta, com credenciais próprias (`THREADS_APP_ID`/`THREADS_APP_SECRET`).
- **Premissa:** o redirect do Threads exige **HTTPS**; em desenvolvimento usamos um **túnel** (URL que muda a cada vez) e, em produção, um domínio com TLS.
- **Risco:** em modo Desenvolvimento só testadores do Threads com perfil **público** autorizam; o convite precisa ser aceito.
- **Risco:** token de 60 dias vencer sem uso → a conta cai em "Reconexão necessária" (aceito; sem renovação em segundo plano).
- **Risco:** regras de contagem dos 500 caracteres (emoji, links) podem divergir da contagem do Hub → validar com margem e tratar o erro da Meta.
- **Risco:** limite de 250 posts por 24 h por perfil → tratar o erro de limite com mensagem amigável.
- **Risco:** o comportamento real da API (tempo entre criar e publicar o container, formato da resposta) difere do documentado → UAT com o perfil de teste.
- **Risco:** o túnel expõe o Hub à internet durante os testes → senha forte e fechar o túnel ao terminar.
