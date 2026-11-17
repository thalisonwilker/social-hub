---
name: glossary
description: Linguagem ubíqua. Puxe ao nomear, modelar domínio ou escrever specs.
alwaysApply: false
---

# Glossário — Linguagem Ubíqua

> A fonte única do vocabulário do sistema. O mesmo termo aparece aqui, na spec e no código.
> Termo novo introduzido por uma feature → adicione no mesmo PR. Sem sinônimos.

| Termo        | Definição                                      | NÃO confundir com | Contexto (bounded context) |
|--------------|------------------------------------------------|-------------------|----------------------------|
| Alvo da publicação | Par (Publicação, Página) com o estado e o resultado do envio àquela Página. | Conta social | Social |
| Conectar | Criar/atualizar uma Conta social a partir de uma Página selecionada. | Fazer login no Social Hub | Social |
| `config_id` | Identificador da configuração de login (permissões e tipo de token) na Meta. | `app_id` | Social |
| Conta social | Identidade conectada numa rede (aqui, uma Página do Facebook) pertencente a um usuário. | Usuário do Social Hub (`User`) | Social |
| Desconectar | Apagar localmente a Conta social e o token. | Revogar o app na Meta | Social |
| Lote | Conjunto de até 5 alvos enviados numa única requisição. | Publicação | Social |
| Post | O que a Meta cria no Facebook; identificado por `post_id` e link permanente. | Publicação | Social |
| Publicar | Enviar o conteúdo de um alvo à Meta e registrar o resultado. | Conectar | Social |
| Publicação | Conteúdo (texto + 1 imagem) a ser publicado em uma ou mais Páginas. | Post | Social |

| Página | Página do Facebook administrada pelo usuário na Meta. | Perfil pessoal | Social |
| Reconexão necessária | Estado da Conta social cujo token expirou, foi revogado ou perdeu permissão. | Conta desconectada | Social |
| Reivindicar | Marcar atomicamente um alvo como `sending` para que só uma requisição o envie. | Bloquear | Social |
| Seleção de Páginas | Passo em que o usuário marca quais Páginas conectar (uma ou várias). | Autorização na Meta | Social |
| Tentar de novo | Reenviar apenas os alvos `failed` ou `pending`, nunca os `published`. | Republicar | Social |
| Token de Página | Credencial da Meta para agir como a Página; guardada criptografada. | Token de usuário | Social |
| Token de usuário | Credencial da pessoa na Meta, usada só para descobrir Páginas; não é persistida. | Token de Página | Social |
<!-- Mantenha em ordem alfabética. Cada linha deve ter um dono mental claro. -->
