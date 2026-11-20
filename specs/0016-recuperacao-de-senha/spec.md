---
name: spec
description: Contrato da feature 0016 — recuperação de senha por e-mail (pedido com resposta genérica e idempotência, link de uso único de 30 min com token em hash, limites por IP e conta, redefinição com a política de senha, sessões encerradas, aviso por e-mail). Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Recuperação de senha

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT com SMTP real)
> Tier: **arquitetural (enxuto)** — ver `design.md` e ADR-0017. `AC-N` começam em 1.
> **Substitui** a parte "Esqueci minha senha" do AC-9 da spec 0014: o link passa a levar a `/recuperar-senha/`.

## Resumo
Em `/recuperar-senha/` a pessoa informa o e-mail e sempre vê a mesma mensagem. Se houver conta, recebe um link de uso único que vale 30 minutos. O link abre `/redefinir-senha/`, onde ela escolhe a nova senha (mesma política do cadastro). Depois disso o link e as sessões antigas deixam de valer, ela recebe um aviso por e-mail e vai para o login, sem entrar automaticamente.

## Mensagens e respostas padronizadas
| Situação | HTTP | Mensagem |
|---|---|---|
| Pedido aceito (com ou sem conta, limitado por conta ou repetido) | 302 → `/recuperar-senha/` | "Se o e-mail estiver cadastrado, você receberá instruções para redefinir sua senha." |
| E-mail vazio/mal formado | 400 | "Informe um e-mail válido." |
| Chave de idempotência ausente/fora do formato | 400 | "Não foi possível processar a solicitação. Recarregue a página e tente novamente." |
| Limite por IP | 429 + `Retry-After` | "Muitas solicitações. Tente novamente em alguns minutos." |
| Link inválido, expirado, já usado ou substituído | 400 (página amigável) | "Este link de redefinição é inválido ou expirou. Solicite um novo." + link para `/recuperar-senha/` |
| Senha nova fora da política / não coincide | 400 | mensagens do cadastro (ex.: "A senha precisa de pelo menos uma letra maiúscula.", "As senhas não coincidem.") |
| Senha redefinida | 302 → login | "Sua senha foi redefinida. Faça login com a nova senha." |

## Critérios de aceite

### AC-1: Página de pedido
- **Dado** um visitante (autenticado ou não)
- **Quando** abre `/recuperar-senha/` (também pelo link "Esqueci minha senha" do login)
- **Então** vê o campo E-mail, o botão **Enviar instruções**, o link "Voltar para o login", no layout das telas de login/cadastro; a página tem um UUID em `chave_idempotencia` (gerado no navegador por `crypto.randomUUID()`, com reserva do servidor sem JS)

### AC-2: Validação do e-mail no navegador e no servidor
- **Dado** e-mail vazio ou mal formado (mesma regra do cadastro)
- **Quando** a pessoa tenta enviar
- **Então** o navegador impede o envio e mostra "Informe um e-mail válido." junto ao campo (`aria-invalid`, `aria-live`); no servidor a mesma entrada recebe 400 com a mesma mensagem e nada é registrado nem enviado. O e-mail é aparado e convertido para minúsculas

### AC-3: Resposta pública igual com e sem conta
- **Dado** um e-mail com conta ativa, um sem conta, uma conta inativa ou um pedido barrado pelo limite por conta
- **Quando** o pedido é enviado
- **Então** a resposta é a mesma nos quatro casos (302 para a mesma página, mesma mensagem genérica, mesmo HTML) e o envio do e-mail acontece fora da requisição, para o tempo não revelar a conta. Só a conta ativa e dentro do limite recebe e-mail

### AC-4: E-mail com link seguro
- **Dado** um pedido para uma conta ativa dentro do limite
- **Quando** o e-mail é enviado
- **Então** ele vai para o e-mail da conta, em pt-BR, com o link `<base>/redefinir-senha/?token=<token>` (base = `PUBLIC_BASE_URL` ou a origem validada da requisição), o aviso de que vale 30 minutos e uma vez só, e "se não foi você, ignore este e-mail". O token tem 256 bits (`secrets.token_urlsafe(32)`) e o banco guarda só o SHA-256 dele; o link anterior da mesma conta deixa de valer

### AC-5: Idempotência do pedido
- **Dado** um pedido já registrado com a chave `K`
- **Quando** chega outra requisição com `K` (reenvio, duplo clique, requisições simultâneas)
- **Então** a resposta é a mesma mensagem genérica, sem novo e-mail, sem novo token e sem contar de novo no limite

### AC-6: Limites por IP e por conta
- **Dado** a janela de 15 min por IP e de 1 hora por conta
- **Quando** um IP faz o 6º pedido em 15 min, ou uma conta já recebeu 1 e-mail na última hora
- **Então** o IP recebe 429 com `Retry-After` (para qualquer e-mail); a conta não recebe outro e-mail, mas a resposta pública continua a do AC-3. Pedidos com campo ou chave inválidos não contam

### AC-7: Abrir o link
- **Dado** um link válido
- **Quando** é aberto
- **Então** o servidor guarda na sessão apenas a referência do token validado e redireciona (302) para `/redefinir-senha/` sem o token na URL; o redirecionamento leva `Referrer-Policy: no-referrer` (a página do formulário não, para o CSRF aceitar o `Origin` do POST); a página mostra **Nova senha**, **Confirmar senha** (com mostrar/ocultar e a lista de requisitos), o botão **Redefinir senha** e "Voltar para o login"

### AC-8: Link inválido, expirado, usado ou substituído
- **Dado** um token inexistente, com mais de 30 min, já usado, substituído por um pedido mais novo, ou da conta que já trocou a senha
- **Quando** o link é aberto ou o formulário é enviado
- **Então** aparece a página amigável (400) "Este link de redefinição é inválido ou expirou. Solicite um novo." com link para `/recuperar-senha/`, sem dizer qual foi o motivo e sem formulário

### AC-9: Nova senha com a política da aplicação
- **Dado** a página de redefinição com link válido
- **Quando** a nova senha não atende à política (≥ 8, maiúscula, número, caractere especial, mais os validadores do Django: comum, só números, parecida com nome/e-mail) ou a confirmação difere
- **Então** o navegador mostra os erros e mantém o botão desabilitado; o servidor recusa com 400 e as mesmas mensagens junto aos campos, sem consumir o token

### AC-10: Redefinição de uso único
- **Dado** um link válido e senhas válidas
- **Quando** o formulário é enviado (uma ou mais vezes, inclusive em paralelo)
- **Então** só um envio consome o token (UPDATE condicional); a senha é gravada com o hash do Django; todos os outros tokens da conta são invalidados; o usuário **não** é autenticado; redireciona ao login com "Sua senha foi redefinida. Faça login com a nova senha."; os demais envios caem no AC-8

### AC-11: Sessões encerradas
- **Dado** sessões abertas da conta (outros navegadores)
- **Quando** a senha é redefinida
- **Então** todas as sessões da conta são apagadas; a próxima requisição desses navegadores cai no login

### AC-12: Aviso de senha alterada
- **Dado** uma redefinição concluída
- **Quando** o servidor termina
- **Então** a conta recebe um e-mail em pt-BR "Sua senha do Social Hub foi alterada" com data/hora e a orientação de pedir uma nova recuperação se não foi ela — sem link de redefinição nem senha

### AC-13: Estados de carregamento, sucesso e erro
- **Dado** as duas páginas com JavaScript
- **Quando** a pessoa envia um formulário válido
- **Então** o botão mostra indicador e "Enviando…"/"Redefinindo…", fica desabilitado e há um envio só (voltar pelo histórico reseta); a mensagem de sucesso aparece num alerta de sucesso e os erros num alerta de erro / junto aos campos

### AC-14: Nada sensível em logs nem no banco
- **Dado** qualquer pedido, abertura de link, redefinição ou falha de envio
- **Quando** o servidor registra
- **Então** logs têm só evento, IP e prefixo do hash do e-mail — nunca token, link, senha, e-mail em claro ou id da sessão; o log de acesso do gunicorn e do `runserver` não contém a query string; o banco guarda só o hash do token; pedidos e tokens com mais de 24 h são apagados

## Matriz de decisão — POST /recuperar-senha/
| Campo/chave válidos | Chave já vista | IP no limite | Conta ativa | Conta no limite | Resultado | AC |
|---|---|---|---|---|---|---|
| não | — | — | — | — | 400 | AC-2 |
| sim | sim | — | — | — | 302 genérico, nada novo | AC-5 |
| sim | não | sim | — | — | 429 | AC-6 |
| sim | não | não | não (sem conta/inativa) | — | registra pedido; 302 genérico; sem e-mail | AC-3 |
| sim | não | não | sim | sim | registra pedido; 302 genérico; sem e-mail | AC-3, AC-6 |
| sim | não | não | sim | não | registra pedido; invalida links antigos; novo token; e-mail após commit; 302 genérico | AC-3, AC-4 |

## Casos de borda e erros
- SMTP fora do ar: o pedido continua com a resposta genérica; o erro vai ao log sem conteúdo do e-mail; o token criado continua válido por 30 min (novo pedido só depois do limite por conta).
- Conta sem e-mail no campo e com username = e-mail (cadastro): o e-mail vai para o username.
- Pessoa autenticada pode pedir e redefinir; após redefinir, a própria sessão também é encerrada.
- Abrir o link em outro navegador que não o da sessão: funciona (o link carrega o token); a sessão de quem abriu passa a guardar a referência.
- Envio sem CSRF → 403.

## Fora de escopo
- Login automático após redefinir; 2FA; troca de e-mail; e-mails em HTML elaborado; fila persistente de e-mails.
- Limites no POST da redefinição (o token de 256 bits torna adivinhar inviável).

## Rastreabilidade
- Product: `./product.md` · Design: `./design.md` · Domínio: `./domain.md` · Tasks: `./tasks.md`
- ADRs: [ADR-0017](../../docs/architecture/adr/0017-envio-de-e-mail-smtp-e-recuperacao-de-senha-com-token-em-hash.md), [ADR-0016](../../docs/architecture/adr/0016-limitacao-de-tentativas-e-idempotencia-do-login-no-banco.md), [ADR-0008](../../docs/architecture/adr/) (log sem query)
- Spec relacionada: [0014](../0014-jornada-de-login/spec.md) (AC-9 parcialmente substituído)
