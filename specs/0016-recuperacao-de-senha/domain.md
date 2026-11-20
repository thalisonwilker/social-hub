---
name: domain
description: Domínio da feature 0016 — recuperação de senha no contexto Contas de usuário. Puxe ao modelar ou nomear.
alwaysApply: false
---

# Domain Model — Recuperação de senha

## Bounded Context
**Contas de usuário** (app `accounts`), junto com Cadastro (0013) e Login (0014). Não toca o contexto Social.

## Linguagem ubíqua
| Termo | Definição |
|---|---|
| Pedido de recuperação | Solicitação feita em `/recuperar-senha/` com um e-mail e uma chave de idempotência; registrada mesmo quando o e-mail não tem conta. |
| Link de redefinição | URL enviada por e-mail com um token de uso único que vale 30 min. |
| Token de redefinição | Segredo aleatório do link; o banco guarda só o hash SHA-256. |
| Aviso de senha alterada | E-mail enviado depois que a senha é redefinida. |

## Agregados, entidades e value objects
- `PasswordResetRequest` (registro do pedido): chave (UUID, única), hash do e-mail, IP, se gerou envio, data.
- `PasswordResetToken` (entidade): usuário, hash do token (único), criado em, expira em, usado em, invalidado em. Invariante: válido ⇔ não usado, não invalidado e não expirado; no máximo um válido por usuário.

## Eventos de domínio
- `LinkDeRedefinicaoEmitido` → envia o e-mail com o link.
- `SenhaRedefinida` → invalida todos os tokens da conta, encerra as sessões e envia o aviso.

## Relações com outros contextos
- Usa o mesmo localizador de conta por e-mail do Login (`EmailBackend`) e a mesma política de senha do Cadastro.
