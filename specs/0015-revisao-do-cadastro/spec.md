---
name: spec
description: Contrato da feature 0015 — revisão pontual do cadastro (spec 0013) — botão "Registrar" com carregamento e envio único, mensagem de sucesso nova, unicidade do e-mail normalizado no banco, nomes com acento decomposto, acessibilidade dos erros e e-mail do navegador alinhado ao servidor. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Revisão do cadastro

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT seu)
> Tier: **Pequeno** (spec + tasks). Revisão da [spec 0013](../0013-cadastro-de-usuario/spec.md):
> só corrige o que faltava; o resto da 0013 continua valendo. Os `AC-N` desta spec começam em 1.

## Diagnóstico (o que a revisão encontrou)
| Requisito | Situação na 0013 | Ação |
|---|---|---|
| Campos nome, sobrenome, e-mail, senha, confirmação, aceite com links, ícone do Google | atende | — |
| Validação em tempo real, mensagens pt-BR, botão desabilitado até tudo válido | atende | — |
| Botão chamado **"Registrar"** | chama "Criar conta" | AC-1 |
| Indicador de carregamento e bloqueio de envio duplo no navegador | só desabilita o botão depois do envio; sem indicador; Enter repetido pode enviar 2× | AC-1 |
| Erros do servidor junto aos campos, dados preservados (menos senhas) | atende | — |
| Acessibilidade: erros anunciados e campos marcados como inválidos sem JS | mensagens não são anunciadas; sem JS o campo com erro não tem `aria-invalid` | AC-2 |
| Revalidação no servidor, hash de senha, aceite obrigatório, erros sem detalhe interno | atende | — |
| Nomes reais com acento | acento **decomposto** (ex.: `e` + `◌́`, comum ao colar texto do macOS) é recusado no servidor e aceito no navegador | AC-3 |
| E-mail aparado e em minúsculas no cadastro e no login | atende (recuperação de senha ainda não existe) | — |
| **Unicidade do e-mail normalizado no banco** | garantida só pelo `username` (= e-mail); o campo `email` não tem restrição — contas criadas pelo admin podem repetir o e-mail | AC-4 |
| E-mail recusado no servidor e aceito no navegador (ex.: `a@b.c`, `a..b@x.com`) | o botão habilita e só o servidor recusa | AC-5 |
| Mensagem final "Sua conta foi criada com sucesso! Faça login para continuar." | texto diferente | AC-6 |
| Aceite não pré-selecionado; sem login automático; sucesso só quando concluído | atende | — |

## Critérios de aceite

### AC-1: Botão "Registrar" com carregamento e envio único
- **Dado** a tela de cadastro com JavaScript e todos os campos válidos
- **Quando** a pessoa clica em **Registrar** (ou aperta Enter), uma ou mais vezes
- **Então** só um envio sai; o botão fica desabilitado com indicador de carregamento e o texto "Registrando…", os campos ficam somente leitura; ao voltar pelo histórico a tela sai do carregamento. Sem JavaScript, o botão "Registrar" funciona normalmente

### AC-2: Erros acessíveis
- **Dado** um campo com erro (do navegador ou do servidor)
- **Quando** a mensagem aparece
- **Então** ela fica num elemento ligado ao campo por `aria-describedby`, anunciado por leitores de tela (`aria-live="polite"`), e o campo tem `aria-invalid="true"` — também quando o erro vem do servidor e a página está sem JavaScript

### AC-3: Nomes com acento em qualquer forma Unicode
- **Dado** nome ou sobrenome com acento composto (`José`) ou decomposto (`Jose` + U+0301)
- **Quando** validado no navegador e no servidor
- **Então** ambos aceitam, e o servidor grava o nome na forma composta (NFC)

### AC-4: E-mail normalizado único no banco
- **Dado** a tabela de usuários
- **Quando** se tenta gravar um usuário com e-mail igual a outro ignorando maiúsculas/espaços — pelo cadastro, pelo admin ou em requisições simultâneas
- **Então** o banco recusa (índice único em `lower(email)` para e-mails não vazios); no cadastro a pessoa vê "Este e-mail já está cadastrado." (nunca erro 500). Usuários sem e-mail continuam permitidos

### AC-5: E-mail no navegador alinhado ao servidor
- **Dado** e-mails que o servidor recusa por formato, como `a@b.c`, `a..b@x.com`, `.a@x.com`, `a@x..com`
- **Quando** digitados no cadastro com JavaScript
- **Então** o navegador já mostra "Informe um e-mail válido." e o botão continua desabilitado

### AC-6: Mensagem de sucesso
- **Dado** um cadastro concluído (inclusive a repetição idempotente da spec 0013, AC-11)
- **Quando** a pessoa chega ao login
- **Então** vê exatamente "Sua conta foi criada com sucesso! Faça login para continuar." — e nunca a vê quando o cadastro não foi concluído

## Casos de borda e erros
- Migração do índice com e-mails já repetidos (ignorando maiúsculas) → a migração para com uma mensagem clara dizendo quantos e-mails repetidos existem; ninguém é alterado automaticamente. (Hoje: banco local 0 e container 0.)
- Usuário criado pelo admin com e-mail em caixa mista → continua válido; o índice compara em minúsculas.

## Fora de escopo
> Vinculante.
- Recuperação de senha (não existe; quando existir, usará a mesma normalização — `normalize_email`).
- Limitar tentativas de cadastro, CAPTCHA, confirmação de e-mail.
- Mudar layout, rotas, trava de idempotência ou regras de senha da 0013.

## Rastreabilidade
- Tasks: `./tasks.md`
- Revisa: [spec 0013](../0013-cadastro-de-usuario/spec.md) (AC-1 rótulo do botão, AC-7 texto da mensagem)
