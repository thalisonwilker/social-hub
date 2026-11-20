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
| Alvo apagado | Alvo `published` com `deleted_at`: o post foi apagado na plataforma; o registro continua no histórico. | Alvo Falhou | Social |
| Alvo apagável | Alvo `published`, com id do post, conta ativa, plataforma com exclusão (Facebook/Threads) e ainda não apagado. | Alvo reenviável | Social |
| Apagar na plataforma | Chamar a API da rede para excluir o post de um alvo (Facebook e Threads). Não remove o registro do Hub. | Remover do Hub | Social |
| Alvo em andamento | Alvo do Threads ou do Instagram em `pending`, `sending` ou `failed` (reenviável): ainda pode precisar da imagem. | Alvo publicado | Social |
| Alvo Incerto | Alvo (`uncertain`) cujo envio pode ter sido concluído pela plataforma, mas o Hub não sabe; só o usuário o resolve. | Alvo Falhou (nada foi publicado) | Social |
| Alvo misto | Publicação cujos destinos incluem Páginas do Facebook e perfis do Threads. | Publicação só do Facebook | Social |
| Chamada com efeito | Chamada à plataforma que cria o post (upload do Facebook, `threads_publish`, `sendStatus`). | Chamadas preparatórias (container, estado) | Social |
| Chave da instância | Credencial da instância da Evolution que autoriza enviar pelo número; guardada criptografada, nunca exibida. | Chave global da Evolution (poder total, não usada pelo Hub) | Social |
| Conectar | Criar/atualizar uma Conta social a partir de uma Página selecionada. | Fazer login no Social Hub | Social |
| `config_id` | Identificador da configuração de login (permissões e tipo de token) na Meta. | `app_id` | Social |
| Conta de WhatsApp | Conta social cujo `external_id` é o nome de uma instância da Evolution já pareada; destino do Status. | Perfil/Página (têm OAuth e link) | Social |
| Conta social | Identidade conectada numa rede (aqui, uma Página do Facebook) pertencente a um usuário. | Usuário do Social Hub (`User`) | Social |
| Conta Instagram | `SocialAccount` `platform=instagram`: conta profissional do Instagram vinculada a uma Página conectada (usa o token da Página). | Página do Facebook | Social |
| Container (Instagram) | Objeto criado em `POST /{ig_id}/media` (imagem + legenda) antes de publicar; tem `status_code` (IN_PROGRESS, FINISHED, ERROR, EXPIRED, PUBLISHED). | Container (Threads) | Social |
| Imagem do Instagram | A imagem da publicação entregue ao Instagram em JPEG, em URL pública temporária; PNG é convertido só nessa entrega. | Imagem armazenada | Social |
| Página vinculada | A Página pela qual a Conta Instagram é alcançada (`parent`); remover a Página remove a conta. | Página qualquer | Social |
| Container (Threads) | Objeto intermediário criado antes de publicar no Threads; tem status (IN_PROGRESS, FINISHED, ERROR, EXPIRED, PUBLISHED). | Publicação / Post | Social |
| Container de imagem | Container do Threads criado com `media_type=IMAGE` e `image_url`. | Container de texto | Social |
| Desconectar | Apagar localmente a Conta social e o token. | Revogar o app na Meta | Social |

| Endereço público | Base HTTPS pela qual a Meta alcança o Hub (`PUBLIC_BASE_URL` ou origem do redirect). | `Host` da requisição | Social |
| Enfileirar | Criar ou reenviar um alvo como `pending` sem falar com a plataforma. | Enviar | Social |
| Expiração do token | Instante em que o token deixa de valer; depois dele a conta exige reconexão. | Reconexão necessária (o estado) | Social |
| Fila de envio | Conjunto dos alvos `pending` em ordem de criação (FIFO); não é uma tabela à parte. | Lote | Social |
| Heartbeat do worker | Registro atualizado pelo worker que indica se há worker ativo. | Healthcheck do Gunicorn | Social |
| Instância (Evolution) | Sessão de um número de WhatsApp pareado na Evolution, identificada por um nome. | Número de telefone | Social |
| Lote | Conjunto de até 5 alvos enviados numa única requisição. | Publicação | Social |
| Modo de publicação | `PUBLISH_MODE`: `worker` (fora da requisição) ou `inline` (na requisição, dev/testes). | Plataforma | Social |
| Orçamento da requisição | Tempo máximo que uma requisição de envio pode gastar antes de deixar o restante para "Continuar envio". | Lote (limite de quantidade) | Social |
| Perfil do Threads | Conta do Threads conectada; é uma Conta social com plataforma `threads`. | Página do Facebook | Social |
| Peso do texto | Medida do limite de 500 do Threads (emoji conta por bytes UTF-8). | Número de caracteres | Social |
| Post | O que a Meta cria no Facebook; identificado por `post_id` e link permanente. | Publicação | Social |
| Publicar | Enviar o conteúdo de um alvo à Meta e registrar o resultado. | Conectar | Social |
| Publicação | Conteúdo (texto + 1 imagem) a ser publicado em uma ou mais Páginas. | Post | Social |
| Página | Página do Facebook administrada pelo usuário na Meta. | Perfil pessoal | Social |
| Reconexão necessária | Estado da Conta social cujo token expirou, foi revogado ou perdeu permissão. | Conta desconectada | Social |
| Perfil | Workspace do usuário que agrupa as Contas conectadas; escolhido após o login ("Quem está usando?") e criado por um wizard (nome → redes). | Conta de usuário (login) | Social |
| Reivindicar | Marcar atomicamente um alvo como `sending` para que só uma requisição o envie. | Bloquear | Social |
| Renovar (token) | Trocar o token vigente por um novo de 60 dias, sem o usuário fazer login. | Reconectar (exige login) | Social |
| Resolver (alvo incerto) | Decisão do usuário sobre um alvo Incerto: "Já foi publicado" ou "Reenviar". | Tentar novamente (só para Falhou) | Social |
| Seleção de Páginas | Passo em que o usuário marca quais Páginas conectar (uma ou várias). | Autorização na Meta | Social |
| Status do WhatsApp | Publicação efêmera (≈ 24 h) do WhatsApp, vista pelos contatos do número; único destino do WhatsApp no Hub. | Mensagem para contato ou grupo | Social |
| Tentar de novo | Reenviar apenas os alvos `failed` ou `pending`, nunca os `published`. | Republicar | Social |
| Token da imagem | Valor assinado (HMAC + carimbo de tempo) que identifica a publicação e expira. | Token de acesso do Threads/Página | Social |
| Token de longa duração | Token do Threads válido por 60 dias, renovável depois de 24 h de vida. | Token de Página (não expira) | Social |
| Imagem gerada | Imagem criada por IA (Gemini) na nova publicação; temporária, sanitizada e do dono; vira a imagem da publicação. | Imagem enviada | Social |
| Remover do Hub | Apagar a publicação (ou um alvo) do histórico e a imagem do volume; o post na rede continua. | Apagar na plataforma | Social |
| Token de Página | Credencial da Meta para agir como a Página; guardada criptografada. | Token de usuário | Social |
| Token de usuário | Credencial da pessoa na Meta, usada só para descobrir Páginas; não é persistida. | Token de Página | Social |
| URL pública assinada | URL temporária, com token assinado, que permite à Meta baixar uma imagem sem login. | Rota autenticada de imagem | Social |
| Worker | Processo `run_worker` que reivindica um alvo `pending` por vez e o envia. | Worker do Gunicorn | Social |
<!-- Mantenha em ordem alfabética. Cada linha deve ter um dono mental claro. -->
