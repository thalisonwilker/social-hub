---
name: spec
description: Contrato da feature 0014 — jornada de login por e-mail com validação no navegador e no servidor, mensagem genérica, limitação de tentativas, chave de idempotência por tentativa, estados de carregamento e códigos HTTP padronizados. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Jornada de login

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT seu)
> Tier: **Pequeno + ADR** (spec + tasks + ADR da limitação de tentativas e idempotência no banco).
> Os `AC-N` desta spec são numerados a partir de 1. **Substitui** o trecho do AC-8 da spec 0013
> que dizia "usuários antigos continuam entrando pelo username": agora o login é só por e-mail.

## Resumo
`/entrar/` passa a pedir **e-mail e senha**, valida os campos no navegador e de novo no servidor,
autentica pelo mecanismo do Django e responde sempre **"E-mail ou senha inválidos"** quando a conta
não existe ou a senha está errada. Cada tentativa leva uma **chave de idempotência (UUID)** gerada
pela página; repetições da mesma tentativa repetem o resultado sem criar outra sessão. Falhas em
excesso por e-mail ou por IP bloqueiam por um tempo (HTTP 429). A tela mostra carregamento, sucesso
e erro, o botão do Google e o link "Esqueci minha senha" (os dois sem ação por enquanto).

## Regras de validação (navegador e servidor)
| Campo | Regra | Mensagem (pt-BR) |
|---|---|---|
| E-mail | obrigatório; formato válido; até 254 caracteres; servidor apara e converte para minúsculas | "Informe um e-mail válido." |
| Senha | obrigatória (sem regra de composição no login; não é aparada) | "Informe sua senha." |
| Chave de idempotência | UUID no formato canônico (36 caracteres, hexadecimal com hífens) | — (ver AC-7) |

## Respostas padronizadas (servidor)
| Situação | HTTP | O que o usuário vê | AC |
|---|---|---|---|
| Login válido | 302 → `next` seguro ou seleção de perfil | área protegida | AC-1 |
| Campo inválido | 400 | mensagem do campo (tabela acima) | AC-3 |
| Chave ausente ou fora do formato | 400 | "Não foi possível processar o login. Recarregue a página e tente novamente." | AC-7 |
| Conta inexistente, senha errada ou conta inativa | 401 | "E-mail ou senha inválidos" | AC-2 |
| Repetição de tentativa já concluída com sucesso, navegador ainda sem a sessão nova | 409 | "Esta tentativa de login já foi processada. Recarregue a página." | AC-6 |
| Limite de tentativas atingido | 429 + `Retry-After` | "Muitas tentativas. Tente novamente em alguns minutos." | AC-5 |

## Critérios de aceite

### AC-1: Login válido autentica e leva à área protegida
- **Dado** uma conta ativa com e-mail `fulano@exemplo.com`
- **Quando** a pessoa envia `FULANO@Exemplo.com ` e a senha correta
- **Então** o servidor autentica com `django.contrib.auth.authenticate`/`login` (a chave da sessão é trocada), registra a tentativa como sucesso e redireciona (302) para o `next` quando ele for seguro (mesmo host) ou para a seleção de perfil; `next` externo é ignorado

### AC-2: Mensagem genérica para credenciais inválidas
- **Dado** um e-mail que não existe, um e-mail existente com senha errada, ou uma conta inativa
- **Quando** o login é enviado
- **Então** a resposta é 401 com exatamente "E-mail ou senha inválidos", o mesmo HTML nos três casos (sem dizer qual parte errou) e o e-mail digitado volta preenchido; a senha nunca volta. O tempo de resposta não revela se a conta existe (o hash de senha roda também para contas inexistentes)

### AC-3: Campos validados antes do envio e de novo no servidor
- **Dado** a tela de login
- **Quando** a pessoa tenta enviar com e-mail vazio/mal formado ou senha vazia (com JavaScript)
- **Então** o envio é impedido e as mensagens da tabela aparecem junto aos campos, com o campo marcado como inválido
- **E quando** os mesmos dados chegam ao servidor (sem JavaScript ou burlando o navegador)
- **Então** a resposta é 400 com as mesmas mensagens, nenhuma tentativa de autenticação é feita e nada conta para o limite

### AC-4: Contas antigas entram pelo e-mail
- **Dado** uma conta antiga com username `admin` e e-mail `admin@example.com`, e as contas do cadastro (username = e-mail)
- **Quando** alguém entra com o e-mail, sem diferenciar maiúsculas
- **Então** o login casa o e-mail com o **username** (contas do cadastro) ou, se não houver, com o **campo e-mail** de uma única conta; se o e-mail aparecer em mais de uma conta, não autentica (401 genérico). Entrar com `admin` (sem @) é recusado como e-mail inválido (400)

### AC-5: Limitação de tentativas
- **Dado** a janela de **15 minutos**
- **Quando** um mesmo e-mail (normalizado) acumula **5 falhas** desde o último login bem-sucedido dele, ou um mesmo IP acumula **20 falhas**
- **Então** as próximas tentativas desse e-mail/IP recebem 429 com `Retry-After` (segundos até a falha mais antiga sair da janela) e "Muitas tentativas. Tente novamente em alguns minutos.", **sem** verificar a senha (nem a correta entra) até a janela liberar. Só contam falhas de credencial (AC-2); erros de campo, chave inválida e repetições não contam. O e-mail é guardado só como hash (HMAC com a `SECRET_KEY`)

### AC-6: Repetições da mesma tentativa
- **Dado** uma tentativa já registrada com a chave `K`
- **Quando** chega outra requisição com a mesma `K` (reenvio, duplo envio, nova tentativa após timeout, requisições simultâneas)
- **Então** não há nova autenticação, nova sessão nem nova falha contada:
  - se a tentativa original **teve sucesso** e o navegador já está com a sessão → 302 para a área protegida;
  - se teve sucesso e o navegador **não** está autenticado (requisição em paralelo com o cookie antigo) → 409, sem criar sessão;
  - se a original **falhou** → 401 com a mesma mensagem genérica;
  - se `K` veio com **outro e-mail** → 409.
  A tentativa é gravada com chave única **antes** de chamar `login()`; quem perde a corrida pela chave cai numa das regras acima. Nada de sessão ou token é guardado na tentativa (só chave, hash do e-mail, IP, resultado e data)

### AC-7: Chave de idempotência gerada pela página
- **Dado** a tela de login
- **Quando** ela é renderizada (abertura ou nova exibição após erro)
- **Então** o navegador gera um UUID (`crypto.randomUUID()`) no campo oculto `chave_idempotencia` e o reusa em todos os reenvios dessa tentativa; uma nova exibição da página gera outra chave. Sem JavaScript vale um UUID gerado pelo servidor no próprio HTML. Chave ausente ou fora do formato → 400 com a mensagem da tabela

### AC-8: Estados de carregamento, sucesso e erro na tela
- **Dado** a tela de login com JavaScript
- **Quando** a pessoa envia dados válidos
- **Então** o botão vira "Entrando…" com indicador de carregamento, fica desabilitado e os campos ficam somente leitura (um único envio); ao voltar pelo histórico do navegador a tela sai do carregamento; erros do servidor (400/401/409/429) aparecem num alerta de erro acima do formulário; o aviso de sucesso do cadastro (spec 0013) continua aparecendo

### AC-9: Google e "Esqueci minha senha" sem ação
- **Dado** a tela de login
- **Quando** a pessoa clica em "Continuar com Google" ou em "Esqueci minha senha"
- **Então** nada acontece (sem navegação nem envio); os dois mostram a dica "Em breve"

### AC-10: Nada sensível em log nem no banco
- **Dado** qualquer tentativa (sucesso, falha, bloqueio, repetição, erro de campo)
- **Quando** o servidor registra o evento
- **Então** o log tem só o tipo do evento, o resultado, o IP e um prefixo do hash do e-mail — nunca a senha, o e-mail em claro, a chave de idempotência, o cookie ou a chave da sessão; a tabela de tentativas não tem senha nem dado de sessão; tentativas com mais de 24 h são apagadas a cada novo envio de login

## Matriz de decisão — POST /entrar/
| Campos e chave válidos | Bloqueado (AC-5) | Chave já registrada | Resultado original | Navegador autenticado | Resposta | AC |
|---|---|---|---|---|---|---|
| não (campo) | — | — | — | — | 400, mensagens dos campos | AC-3 |
| não (chave) | — | — | — | — | 400, "Recarregue a página…" | AC-7 |
| sim | — | sim, outro e-mail | — | — | 409 | AC-6 |
| sim | — | sim | sucesso | sim | 302 área protegida | AC-6 |
| sim | — | sim | sucesso | não | 409 | AC-6 |
| sim | — | sim | falha | — | 401 genérico (não conta) | AC-6 |
| sim | sim | não | — | — | 429 + `Retry-After` | AC-5 |
| sim | não | não | credenciais erradas | — | 401 genérico (conta 1 falha) | AC-2, AC-5 |
| sim | não | não | credenciais certas | — | grava tentativa → `login()` → 302 | AC-1 |

> Usuário já autenticado que abre ou envia `/entrar/` é redirecionado antes de tudo (comportamento atual do Django).

## Casos de borda e erros
- `next` apontando para outro host → ignorado (vai para a seleção de perfil).
- Chave reutilizada por outra pessoa/navegador para "pegar carona" num sucesso → 409, sem sessão (a sessão só nasce na requisição que gravou a tentativa).
- IP vem de `REMOTE_ADDR` (o app não confia em `X-Forwarded-For`); atrás de um proxy reverso todos parecem o mesmo IP — revisar ao publicar (ver ADR).
- E-mail com espaços nas pontas é aparado; maiúsculas não importam; a senha não é aparada.
- Envio sem CSRF → 403 (padrão do Django).
- Duas abas com chaves diferentes e credenciais certas → duas sessões no mesmo navegador são a mesma (o cookie é um só); não é duplicidade.

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Login com Google (OAuth) — só o ícone.
- Recuperação de senha — só o link.
- CAPTCHA, bloqueio permanente de conta, aviso por e-mail de tentativas suspeitas, 2FA.
- Login por username sem @.
- Login via API/JSON (o formulário continua HTML enviado pelo navegador, ADR-0015).
- Limitar tentativas no cadastro (`/cadastro/`).

## Rastreabilidade
- Tasks: `./tasks.md`
- ADRs: [ADR-0016](../../docs/architecture/adr/0016-limitacao-de-tentativas-e-idempotencia-do-login-no-banco.md) (limitação de tentativas e idempotência do login no banco); [ADR-0015](../../docs/architecture/adr/0015-interface-mui-ilhas-que-elevam-o-html-do-servidor.md)
- Spec relacionada: [0013 — cadastro](../0013-cadastro-de-usuario/spec.md) (AC-8 parcialmente substituído)
