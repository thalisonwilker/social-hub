---
name: spec
description: Contrato da feature 0013 — cadastro público de novos usuários (nome, sobrenome, e-mail, senha forte, aceite dos termos), e-mail verificado no servidor e sem diferenciar maiúsculas e login por e-mail. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Cadastro de novos usuários

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT seu)
> Tier: **Pequeno** (spec + tasks). Os `AC-N` desta spec são numerados a partir de 1.

## Resumo
Uma pessoa sem conta abre `/cadastro/`, informa **nome, sobrenome, e-mail, senha, confirmação
da senha** e **aceita os Termos de Uso e a Política de Privacidade**. O navegador valida cada
campo enquanto ela digita e só habilita **Criar conta** quando tudo está válido; o servidor
valida tudo de novo. O e-mail é tratado **sem diferenciar maiúsculas** e gravado em minúsculas
(também como `username`). Ao salvar, ela vai para o login com o aviso de conta criada e passa a
entrar com o e-mail. A tela mostra um botão do Google, **sem ação** por enquanto.

## Regras de validação (valem no navegador e no servidor)
| Campo | Regra | Mensagem (pt-BR) |
|---|---|---|
| Nome | obrigatório; 2–150 caracteres após aparar espaços; só letras (com acento), espaço, hífen e apóstrofo; ao menos 2 letras | "Informe seu nome." (vazio ou < 2 letras) / "Use apenas letras, espaços, hífen ou apóstrofo." / "Use no máximo 150 caracteres." |
| Sobrenome | mesma regra do Nome | "Informe seu sobrenome." / idem |
| E-mail | obrigatório; formato válido; até 254 caracteres; **só no servidor:** não pode existir outro usuário com o mesmo e-mail **ou username** sem diferenciar maiúsculas | "Informe um e-mail válido." / "Este e-mail já está cadastrado." |
| Senha | ≥ 8 caracteres, ≥ 1 letra maiúscula, ≥ 1 número, ≥ 1 caractere especial (não letra/número/espaço); no servidor também os validadores padrão do Django (senha comum, parecida com nome/e-mail, só números) | "Informe uma senha." (vazio) ou uma mensagem por regra não atendida, ex.: "A senha precisa de pelo menos uma letra maiúscula." |
| Confirmar senha | igual à senha | "As senhas não coincidem." |
| Aceite | obrigatório (marcado) | "Você precisa aceitar os Termos de Uso e a Política de Privacidade." |

## Critérios de aceite

### AC-1: Tela de cadastro pública
- **Dado** um visitante não autenticado
- **Quando** abre `/cadastro/`
- **Então** vê os campos Nome, Sobrenome, E-mail, Senha (com mostrar/ocultar), Confirmar senha, o checkbox "Li e aceito os Termos de Uso e a Política de Privacidade" (com links para `/termos/` e `/privacidade/`), o botão **Criar conta** desabilitado, o botão do Google e o link "Já tem conta? Entrar"; o login ganha o link "Criar conta" para `/cadastro/`

### AC-2: Usuário autenticado não vê o cadastro
- **Dado** um usuário autenticado
- **Quando** abre `/cadastro/`
- **Então** é redirecionado para `LOGIN_REDIRECT_URL` (seleção de perfil)

### AC-3: Validação no navegador campo a campo
- **Dado** a tela de cadastro com JavaScript ativo
- **Quando** a pessoa sai de um campo (ou digita, após já ter saído dele uma vez) com valor fora das regras
- **Então** o campo mostra a mensagem em pt-BR da tabela de regras; a senha mostra uma lista de requisitos marcados como atendidos/pendentes conforme digita

### AC-4: Botão só habilita com tudo válido
- **Dado** a tela de cadastro com JavaScript ativo
- **Quando** todos os campos atendem às regras do navegador (formato do e-mail incluso) e o aceite está marcado
- **Então** **Criar conta** fica habilitado; se qualquer condição deixar de valer, volta a ficar desabilitado. O navegador **não** consulta o servidor para saber se o e-mail já existe

### AC-5: Servidor revalida tudo
- **Dado** um `POST /cadastro/` com qualquer campo fora das regras (inclusive sem JavaScript, com o botão burlado ou com aceite ausente)
- **Quando** o servidor processa
- **Então** nenhum usuário é criado e a tela volta com os valores digitados (exceto as senhas) e **todas** as mensagens de erro em pt-BR junto aos campos

### AC-6: E-mail verificado no servidor, sem diferenciar maiúsculas
- **Dado** um usuário existente com e-mail `email@email.com`
- **Quando** alguém envia o cadastro com `eMaiL@EMAil.com`
- **Então** o servidor o trata como o mesmo e-mail (consulta só pelo ORM, sem SQL cru): a tela volta com "Este e-mail já está cadastrado." no campo E-mail e nada é criado

### AC-7: Cadastro bem-sucedido
- **Dado** um `POST /cadastro/` válido com e-mail ` Fulano@Exemplo.COM `
- **Quando** o servidor salva
- **Então** cria um usuário ativo, não staff, com `email` e `username` = `fulano@exemplo.com`, `first_name`/`last_name` aparados, senha com hash; **não** inicia sessão; redireciona para o login, que mostra "Sua conta foi criada. Entre com seu e-mail e senha."

### AC-8: Login por e-mail sem diferenciar maiúsculas
> **Parcialmente substituído pela spec 0014 (AC-4):** contas antigas passam a entrar pelo e-mail; o username sem @ não autentica mais.

- **Dado** o usuário criado no AC-7
- **Quando** entra com `FULANO@exemplo.com` e a senha
- **Então** o login conclui; usuários antigos (ex.: `admin`) continuam entrando pelo username como antes; o rótulo do campo passa a ser "E-mail"

### AC-9: Botão do Google sem ação
- **Dado** a tela de cadastro
- **Quando** a pessoa clica em "Continuar com Google"
- **Então** nada acontece (sem navegação nem envio do formulário); o botão mostra o ícone do Google e a dica "Em breve"

### AC-10: Páginas de termos provisórias
- **Dado** um visitante não autenticado
- **Quando** abre `/termos/` ou `/privacidade/`
- **Então** vê uma página pública com o título (Termos de Uso / Política de Privacidade) e o aviso "Documento em elaboração."

### AC-11: Trava de idempotência no envio
- **Dado** que cada abertura de `/cadastro/` (e cada nova exibição do formulário com erros) inclui um campo oculto `chave_idempotencia`, gerado e **assinado** pelo servidor e válido por **2 horas**
- **Quando** chegam ao servidor duas ou mais requisições `POST /cadastro/` com a mesma chave (duplo clique, reenvio do navegador, nova tentativa após timeout, requisições simultâneas)
- **Então** só a primeira é processada e no máximo **um** usuário é criado. A chave é gravada no banco com restrição de unicidade **na mesma transação** que cria o usuário. Uma repetição depois do sucesso **não** mostra "Este e-mail já está cadastrado.": recebe a mesma resposta de sucesso (redireciona ao login com "Sua conta foi criada. Entre com seu e-mail e senha."). A trava é conferida **antes** da validação do e-mail

### AC-12: Chave ausente, inválida ou expirada
- **Dado** um `POST /cadastro/` sem `chave_idempotencia`, com assinatura inválida ou com mais de 2 horas
- **Quando** o servidor processa
- **Então** nada é criado e a tela volta com os dados digitados (exceto as senhas), uma chave nova e o aviso "O formulário expirou. Revise os dados e envie novamente."

## Matriz de decisão — trava de idempotência (servidor)
| Assinatura/validade da chave | Chave já registrada | Dados válidos | Resultado | AC |
|---|---|---|---|---|
| inválida, ausente ou expirada | — | — | volta com o aviso de expiração e uma chave nova; nada criado | AC-12 |
| válida | sim (usuário criado) | — | redireciona ao login com a mensagem de sucesso; nada criado | AC-11 |
| válida | não | não | volta com os erros e uma **chave nova**; a chave não é registrada | AC-5, AC-11 |
| válida | não | sim | registra a chave e cria o usuário na mesma transação → login com sucesso | AC-7, AC-11 |
| válida | não (corrida: outra requisição registra antes) | sim | a restrição de unicidade barra a segunda; ela responde como repetição após sucesso | AC-11 |

## Matriz de decisão — habilitar "Criar conta" (navegador)
| Campos válidos no navegador | Aceite | Botão | AC |
|---|---|---|---|
| não | — | desabilitado | AC-4 |
| sim | não | desabilitado | AC-4 |
| sim | sim | **habilitado** (e-mail repetido é barrado no servidor) | AC-4, AC-6 |

## Casos de borda e erros
- Dois envios simultâneos com o mesmo e-mail e **chaves diferentes** (ex.: duas abas): o `username` único barra o segundo → "Este e-mail já está cadastrado." (sem erro 500). Com a **mesma chave**, vale o AC-11.
- A trava fica no banco, não em cache: hoje há 2 workers do gunicorn sem cache compartilhado.
- Repetição em que a primeira requisição falhou com erro 500 (transação desfeita): a chave não ficou registrada, então a repetição é processada normalmente.
- E-mail igual ao **username** de um usuário antigo (ex.: username `ana@x.com` sem e-mail) → conta como já cadastrado.
- Entradas com `<script>`, aspas ou `' OR 1=1 --` no nome/e-mail: rejeitadas pelas regras; nada é refletido sem escape (autoescape do template) nem concatenado em SQL.
- Espaços nas pontas de nome/sobrenome/e-mail são aparados; a senha **não** é aparada.
- Envio sem CSRF → 403 (padrão do Django).
- Sem JavaScript: o formulário funciona (o botão nasce desabilitado só via JS — sem JS ele fica habilitado) e o servidor valida (AC-5).

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Login/cadastro com Google (OAuth) — só o ícone.
- Checar no navegador (AJAX/endpoint) se o e-mail já existe — a verificação é só no servidor, no envio.
- E-mail de confirmação, verificação de domínio (DNS/MX), recuperação de senha.
- Login automático após o cadastro.
- Texto jurídico real dos Termos e da Política; registrar data/versão do aceite.
- Aplicar a regra de composição de senha à troca de senha em "Minha conta" (continua com os validadores atuais).
- Limpeza automática das chaves de idempotência antigas (cada linha é pequena; vira backlog).
- CAPTCHA e limitação de tentativas no `POST /cadastro/` e no login (backlog: django-axes).

## Rastreabilidade
- Tasks: `./tasks.md`
- ADRs relacionados: [ADR-0015](../../docs/architecture/adr/0015-interface-mui-ilhas-que-elevam-o-html-do-servidor.md) (MUI eleva o HTML do servidor)
