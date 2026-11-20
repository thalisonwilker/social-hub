---
name: spec
description: Contrato da feature 0011 — Perfis (workspaces), seleção de perfil pós-login, wizard de criação/conexão e novo layout de login. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Perfis, seleção de perfil e wizard de conexão

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT real)
> Os `AC-N` desta spec são numerados a partir de 1.

## Resumo
Depois do login o usuário escolhe um **Perfil** (workspace, estilo "Quem está usando?"). Cada Perfil agrupa as Contas conectadas (Facebook, Instagram, Threads, WhatsApp). Sem Perfis aparece só o **+**. Criar um Perfil é um **wizard**: nome → ícones das redes para conectar → dashboard. Twitter/X e TikTok aparecem como "Em breve". O login ganha um layout novo (dois painéis, mostrar/ocultar senha).

## Critérios de aceite

### AC-1: Login leva à seleção de perfil
- **Dado** um usuário que entra com credenciais válidas
- **Quando** o login conclui (sem `next`)
- **Então** ele cai em `/perfis/` e nenhum Perfil está ativo na sessão

### AC-2: Sem perfis, só o "+"
- **Dado** um usuário sem Perfis
- **Quando** abre `/perfis/`
- **Então** vê apenas o cartão "+" (Novo perfil) apontando para o wizard

### AC-3: Escolher um perfil abre o painel
- **Dado** um usuário com Perfis
- **Quando** escolhe um (`POST /perfis/<id>/entrar/`)
- **Então** o perfil fica ativo na sessão e ele vai ao dashboard; perfil de outro usuário → 404

### AC-4: Wizard passo 1 — nome
- **Dado** o formulário de nome em `/perfis/novo/`
- **Quando** o usuário confirma um nome válido (1–60 caracteres, sem repetir nome dele)
- **Então** o Perfil é criado, fica ativo e ele segue ao passo 2; nome vazio ou repetido mostra erro e não cria nada

### AC-5: Wizard passo 2 — ícones das redes
- **Dado** o passo 2 (`/perfis/<id>/conectar/`, só do dono)
- **Quando** a tela abre
- **Então** mostra os ícones Facebook, Instagram, Threads e WhatsApp para conectar, e Twitter/X e TikTok desabilitados como "Em breve"

### AC-6: Conexão vincula ao perfil e termina no dashboard
- **Dado** o passo 2 ativo e uma conexão concluída (Página do Facebook, Instagram vinculado, Threads ou WhatsApp)
- **Quando** o retorno chega
- **Então** as contas novas ficam vinculadas ao Perfil, e o usuário vai ao **dashboard**; falha ou cancelamento volta ao passo 2

### AC-7: Pular a conexão
- **Dado** o passo 2
- **Quando** o usuário clica "Concluir" sem conectar
- **Então** vai ao dashboard do Perfil (as redes podem ser conectadas depois em Contas conectadas)

### AC-8: Isolamento por perfil
- **Dado** um Perfil ativo
- **Quando** o usuário abre Contas conectadas, o dashboard ou escolhe destinos em Nova publicação
- **Então** só vê as contas daquele Perfil; sem Perfil ativo (usuário sem Perfis) tudo continua como antes

### AC-9: Dashboard exige perfil ativo
- **Dado** um usuário que tem Perfis mas nenhum ativo
- **Quando** abre o dashboard
- **Então** é redirecionado para `/perfis/`

### AC-10: Dados existentes migram
- **Dado** usuários que já têm contas
- **Quando** a migração roda
- **Então** cada um ganha o Perfil "Principal" com todas as suas contas

### AC-11: Isolamento entre usuários
- **Dado** dois usuários
- **Quando** um tenta ver, ativar ou conectar o Perfil do outro
- **Então** recebe 404; `/perfis/` lista só os seus

### AC-12: Novo layout de login
- **Dado** a tela de login
- **Quando** abre
- **Então** exibe painel de marca e formulário (usuário, senha com mostrar/ocultar, Entrar); credenciais inválidas mostram o erro

## Fora de escopo (vinculante)
- Conectar Twitter/X e TikTok de fato (só ícone "Em breve").
- Renomear/excluir Perfil; compartilhar Perfil entre usuários; mover conta entre Perfis.
- Escopar publicações já feitas por Perfil (o histórico continua por usuário).
