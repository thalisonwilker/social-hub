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
| Alvo em andamento | Alvo do Threads em `pending`, `sending` ou `failed` (reenviável): ainda pode precisar da imagem. | Alvo publicado | Social |
| Alvo misto | Publicação cujos destinos incluem Páginas do Facebook e perfis do Threads. | Publicação só do Facebook | Social |
| Chave da instância | Credencial da instância da Evolution que autoriza enviar pelo número; guardada criptografada, nunca exibida. | Chave global da Evolution (poder total, não usada pelo Hub) | Social |
| Conectar | Criar/atualizar uma Conta social a partir de uma Página selecionada. | Fazer login no Social Hub | Social |
| `config_id` | Identificador da configuração de login (permissões e tipo de token) na Meta. | `app_id` | Social |
| Conta de WhatsApp | Conta social cujo `external_id` é o nome de uma instância da Evolution já pareada; destino do Status. | Perfil/Página (têm OAuth e link) | Social |
| Conta social | Identidade conectada numa rede (aqui, uma Página do Facebook) pertencente a um usuário. | Usuário do Social Hub (`User`) | Social |
| Container (Threads) | Objeto intermediário criado antes de publicar no Threads; tem status (IN_PROGRESS, FINISHED, ERROR, EXPIRED, PUBLISHED). | Publicação / Post | Social |
| Container de imagem | Container do Threads criado com `media_type=IMAGE` e `image_url`. | Container de texto | Social |
| Desconectar | Apagar localmente a Conta social e o token. | Revogar o app na Meta | Social |

| Endereço público | Base HTTPS pela qual a Meta alcança o Hub (`PUBLIC_BASE_URL` ou origem do redirect). | `Host` da requisição | Social |
| Expiração do token | Instante em que o token deixa de valer; depois dele a conta exige reconexão. | Reconexão necessária (o estado) | Social |
| Instância (Evolution) | Sessão de um número de WhatsApp pareado na Evolution, identificada por um nome. | Número de telefone | Social |
| Lote | Conjunto de até 5 alvos enviados numa única requisição. | Publicação | Social |
| Orçamento da requisição | Tempo máximo que uma requisição de envio pode gastar antes de deixar o restante para "Continuar envio". | Lote (limite de quantidade) | Social |
| Perfil do Threads | Conta do Threads conectada; é uma Conta social com plataforma `threads`. | Página do Facebook | Social |
| Peso do texto | Medida do limite de 500 do Threads (emoji conta por bytes UTF-8). | Número de caracteres | Social |
| Post | O que a Meta cria no Facebook; identificado por `post_id` e link permanente. | Publicação | Social |
| Publicar | Enviar o conteúdo de um alvo à Meta e registrar o resultado. | Conectar | Social |
| Publicação | Conteúdo (texto + 1 imagem) a ser publicado em uma ou mais Páginas. | Post | Social |
| Página | Página do Facebook administrada pelo usuário na Meta. | Perfil pessoal | Social |
| Reconexão necessária | Estado da Conta social cujo token expirou, foi revogado ou perdeu permissão. | Conta desconectada | Social |
| Reivindicar | Marcar atomicamente um alvo como `sending` para que só uma requisição o envie. | Bloquear | Social |
| Renovar (token) | Trocar o token vigente por um novo de 60 dias, sem o usuário fazer login. | Reconectar (exige login) | Social |
| Seleção de Páginas | Passo em que o usuário marca quais Páginas conectar (uma ou várias). | Autorização na Meta | Social |
| Status do WhatsApp | Publicação efêmera (≈ 24 h) do WhatsApp, vista pelos contatos do número; único destino do WhatsApp no Hub. | Mensagem para contato ou grupo | Social |
| Tentar de novo | Reenviar apenas os alvos `failed` ou `pending`, nunca os `published`. | Republicar | Social |
| Token da imagem | Valor assinado (HMAC + carimbo de tempo) que identifica a publicação e expira. | Token de acesso do Threads/Página | Social |
| Token de longa duração | Token do Threads válido por 60 dias, renovável depois de 24 h de vida. | Token de Página (não expira) | Social |
| Token de Página | Credencial da Meta para agir como a Página; guardada criptografada. | Token de usuário | Social |
| Token de usuário | Credencial da pessoa na Meta, usada só para descobrir Páginas; não é persistida. | Token de Página | Social |
| URL pública assinada | URL temporária, com token assinado, que permite à Meta baixar uma imagem sem login. | Rota autenticada de imagem | Social |
<!-- Mantenha em ordem alfabética. Cada linha deve ter um dono mental claro. -->
