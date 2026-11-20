---
name: product
description: Product da feature 0016 — recuperação de senha por e-mail. Puxe ao discutir escopo/valor da feature.
alwaysApply: false
---

# Product — Recuperação de senha

## Problema
Quem esquece a senha hoje não tem como voltar a entrar: o link "Esqueci minha senha" (spec 0014) não faz nada e só o admin pode trocar a senha de alguém.

## Para quem
Usuários do Social Hub que se cadastraram (spec 0013) ou contas antigas com e-mail.

## Resultado esperado / métrica de sucesso
- A pessoa redefine a senha sozinha, pelo link enviado ao e-mail, em poucos minutos.
- Nenhuma resposta pública permite descobrir se um e-mail tem conta.
- Zero tokens ou senhas em logs e no banco (só hash).

## Goals
- Solicitar o link por e-mail; redefinir a senha com a política atual; ser avisado da troca.

## Non-goals
- Login automático após redefinir, 2FA, perguntas de segurança, SMS, recuperação por suporte.

## Riscos / premissas
- Precisa de um SMTP configurado no `.env` para funcionar fora do desenvolvimento.
- Caixa de spam e atraso do provedor de e-mail estão fora do controle do app.
