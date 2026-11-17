---
name: ADR-0002
description: Tokens de Página da Meta ficam criptografados (Fernet) no SQLite, com chave no .env.
alwaysApply: false
---

# ADR-0002: Tokens de Página criptografados com Fernet (chave no `.env`)

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A feature `0002-facebook-page-connect` guarda o token de acesso de cada Página do Facebook conectada. Com esse
token, quem o possuir age como a Página (e, nas próximas etapas, publica em nome dela). O banco é um arquivo
SQLite em volume Docker, sujeito a backup, cópia e vazamento. Não há cofre de segredos nem KMS na infra atual,
e criar um seria desproporcional a esta etapa.

## Decisão
Vamos **criptografar cada token em repouso com Fernet** (biblioteca `cryptography`), usando a chave de
`META_TOKEN_ENCRYPTION_KEY` do `.env`.
- Suporte a **rotação** com `MultiFernet`: a variável aceita várias chaves separadas por vírgula; a primeira
  criptografa, todas descriptografam.
- O token **nunca** é exibido, logado nem incluído em `repr`/admin; só é descriptografado no momento do uso.
- Tokens pendentes de seleção, guardados na sessão, também ficam criptografados.
- Alternativas descartadas: **texto puro** (vazamento do SQLite expõe as Páginas) e **cofre externo
  Vault/KMS** (infra nova desproporcional; fica como evolução futura).

## Consequências
- **+** Vazamento apenas do banco ou do backup não revela os tokens.
- **+** Rotação de chave sem perder dados; sem infra nova.
- **−** A chave no `.env` precisa de backup e cuidado: perdê-la torna os tokens ilegíveis (a recuperação é reconectar).
- **−** Quem tiver banco **e** `.env` ainda acessa os tokens; o cofre externo fica como dívida consciente.
- **−** Nova dependência (`cryptography`).
