# Social Hub

Plataforma web para centralizar o gerenciamento e a publicação de conteúdos em redes sociais (Facebook, Instagram e Threads).

> **Estado atual:** estrutura base, autenticação, dashboard (dados **demonstrativos**), infraestrutura Docker,
> **integração com Páginas do Facebook** (conectar, listar, verificar e desconectar), **publicação de texto + imagem
> em uma ou várias Páginas**, **Threads** (conectar perfil e publicar texto e imagem, junto ou separado do Facebook) e
> **Status do WhatsApp** (via uma Evolution API sua, texto e imagem).
> Agendamento e insights reais **ainda não** foram implementados.

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | Python 3.13 + Django 5.2 LTS |
| Frontend | Django Templates, HTML5, CSS3 (Tailwind CSS 3), JavaScript puro |
| Ícones / fonte | Lucide e Inter (servidos localmente, sem CDN) |
| Banco | SQLite (modo WAL) |
| Servidor | Gunicorn + WhiteNoise (estáticos) |
| Infra | Docker e Docker Compose |

## Executando com Docker (recomendado)

```bash
cp .env.example .env        # depois edite o .env (veja abaixo)
docker compose up --build -d
```

Acesse **http://localhost:8000** (ou a porta definida em `WEB_PORT`).
No primeiro start, o usuário administrador é criado a partir de `DJANGO_SUPERUSER_*` do `.env`.

Antes de subir, edite o `.env`:

- `DJANGO_SECRET_KEY`: **obrigatória** (mín. 32 caracteres). Gere com `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
- `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD`: credenciais do admin inicial.
- `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS`: ajuste ao publicar em um domínio.

### Comandos úteis

```bash
docker compose logs -f web                              # logs
docker compose ps                                       # status e healthcheck
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test           # testes
docker compose down                                     # para (mantém os dados)
docker compose down -v                                  # para e APAGA o banco
```

## Desenvolvimento local (sem Docker)

Requer Python 3.13+ e Node 20+ (Node só é usado para compilar o CSS).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install && npm run build      # gera static/dist (CSS, Lucide, Inter)
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver        # usa config.settings.dev
```

Em outro terminal, `npm run watch` recompila o Tailwind a cada alteração nos templates.

## Estrutura

```
config/                 Projeto Django
  settings/base.py      Configuração comum (lê variáveis de ambiente / .env)
  settings/dev.py       Desenvolvimento (DEBUG, SECRET_KEY padrão)
  settings/prod.py      Produção (DEBUG off, SECRET_KEY obrigatória, HTTPS opcional)
apps/
  core/                 Healthcheck, navegação da sidebar, view de páginas reservadas
  accounts/             Login, logout, perfil, troca de senha, comando ensure_admin
  dashboard/            Dashboard (dados fictícios em demo.py)
  social/               Integração com a Meta: contas, OAuth, cliente Graph API, tokens cifrados, publicações e imagens
templates/              layout.html (sidebar + header + conteúdo), partials, páginas
frontend/               Fonte do Tailwind (input.css, tailwind.config.js) e cópia de vendors
static/js/app.js        Tema claro/escuro, menu mobile e Lucide
static/dist/            Assets compilados (não versionado; gerado por `npm run build`)
docker/entrypoint.sh    migrate + criação do admin + start do Gunicorn
Dockerfile              Multi-stage: Node compila o frontend, Python executa o app
docker-compose.yml      Serviço web + volumes `sqlite_data` (banco) e `media_data` (imagens)
```

Decisões relevantes:

- **Login obrigatório global** via `LoginRequiredMiddleware`: toda nova view é protegida por padrão; só quem usa `@login_not_required` (login e `/healthz/`) é pública.
- **Tema** por variáveis CSS (`frontend/input.css`); o modo escuro só troca valores, e a escolha fica em `localStorage`.
- **Navegação** em um único lugar: `apps/core/context_processors.py`.

## Integração com o Facebook (Páginas)

Permite que cada usuário conecte sua conta Meta, **escolha uma ou várias Páginas** e as gerencie em *Contas conectadas*.
Os tokens de Página ficam **criptografados** (Fernet) no SQLite. Detalhes: `specs/0002-facebook-page-connect/`.

### Configurar o app na Meta
1. Em [Meta for Developers](https://developers.facebook.com), crie um app com o caso de uso **Gerenciar tudo na sua Página**.
2. Em **Casos de uso → Personalizar**, adicione `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` e `read_insights`.
3. Em **Login do Facebook para Empresas → Configurações**: ative *Login OAuth do cliente/da Web* e cadastre em
   *URIs de redirecionamento válidos* o valor de `META_REDIRECT_URI`.
4. Em **Login do Facebook para Empresas → Configurações → Criar configuração**: token de acesso do usuário e as
   permissões acima. Copie o **ID da configuração** (`META_LOGIN_CONFIG_ID`).
5. Em **Configurações do app → Básico**, copie **App ID** e **Chave Secreta**.
6. Enquanto o app estiver em modo *Desenvolvimento*, só contas com função no app conseguem autorizar.

### Variáveis no `.env`
`META_APP_ID`, `META_APP_SECRET`, `META_LOGIN_CONFIG_ID`, `META_REDIRECT_URI` (idêntica à cadastrada na Meta),
`META_GRAPH_VERSION` (padrão `v27.0`) e `META_TOKEN_ENCRYPTION_KEY`. Gere a chave com:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Sem essas variáveis o sistema sobe normalmente e *Contas conectadas* mostra "Integração com a Meta não configurada".

### Operação e segurança
- **Faça backup da `META_TOKEN_ENCRYPTION_KEY`** separado do banco. Sem ela os tokens ficam ilegíveis (a recuperação é reconectar).
- **Rotação da chave:** coloque a nova **primeiro**, separada por vírgula da antiga (`NOVA,ANTIGA`); depois que todas as
  contas forem reconectadas/regravadas, remova a antiga.
- Se o **App Secret** vazar, redefina-o no painel da Meta e atualize o `.env`.
- Desconectar uma Página apaga o token só no Social Hub; para revogar de vez, remova o app em *Configurações do Facebook → Integrações*.
- Em produção o `META_REDIRECT_URI` precisa ser **HTTPS** (`DJANGO_SECURE_SSL=true` atrás de um proxy com TLS).

## Publicações (texto + imagem em várias Páginas)

Em **Publicações → Nova publicação**: escreva o texto (até 5000 caracteres), anexe **uma imagem** (JPEG ou PNG, até 8 MB),
marque **uma ou várias Páginas** ativas e clique em *Publicar agora*. O resultado aparece **por Página** (link do post ou o
motivo do erro) e você pode **tentar de novo só as que falharam**. Detalhes: `specs/0003-publicar-no-facebook/`.

- **Teste primeiro em Páginas de teste:** a publicação é real e o Hub **não** exclui nem edita posts já publicados.
- **Envio em segundo plano:** em produção *Publicar* só **enfileira** e o **worker** envia (veja a seção abaixo). O lote de 5 Páginas (`PUBLISH_BATCH_SIZE`) e o **Continuar envio** valem só no modo `inline` (desenvolvimento/testes).
- **Sem duplicar:** uma Página já publicada nunca é reenviada; cliques duplos não geram posts repetidos.
- **Imagens:** são validadas e **re-encodadas** (metadados como localização são removidos), guardadas no volume
  `media_data` (`/media`) e entregues só ao dono, sem URL pública.
- **Timeout:** o Gunicorn roda com `--timeout 180` (no modo `inline`, 5 uploads de até 30 s por lote); no modo `worker` a requisição responde na hora.
- **Backup do volume de imagens:** sem ele o histórico perde as miniaturas (os posts já publicados na Meta não são afetados).
  Exemplo: `docker run --rm -v social-hub_media_data:/media -v "$PWD":/backup alpine tar czf /backup/media.tgz -C /media .`
- **Sem duplicar às cegas:** se o Hub não souber se a plataforma publicou (tempo esgotado, conexão cortada, worker reiniciado), o alvo fica **Incerto** e nunca é reenviado sozinho: veja a seção abaixo.


## Threads (perfil + texto + imagem)

Conecta um perfil do Threads (login próprio) e publica **texto e imagem** nele — sozinho ou **junto com Páginas do Facebook** no mesmo
formulário. O texto vai até 500 de "peso" (emoji contam por bytes; no máximo 5 links diferentes); a imagem é obrigatória apenas se
houver Página do Facebook marcada e, quando existe, **vai também ao Threads** (proporção até 10:1). Detalhes:
`specs/0004-threads-conectar-e-publicar/` e `specs/0005-threads-imagem/`.

### Configurar o app na Meta
1. No app, adicione o caso de uso **Acessar a API do Threads** e, em *Permissões e recursos*, `threads_basic` e `threads_content_publish`.
2. Nas **configurações do caso de uso do Threads**: copie o **ID do app do Threads** e a **chave secreta do app do Threads**
   (são **diferentes** das do app principal) e cadastre em *Redirecionar URLs de callback* o valor de `THREADS_REDIRECT_URI` — **HTTPS obrigatório**.
   Deixe vazios os callbacks de desinstalação e exclusão por enquanto.
3. Em **Funções do app → Funções**, adicione seu usuário como **Testador do Threads** e **aceite o convite no Threads**
   (*Configurações → Conta → Permissões de sites → Convites*). O perfil precisa ser **público**.

### Variáveis no `.env`
`THREADS_APP_ID`, `THREADS_APP_SECRET`, `THREADS_REDIRECT_URI` (HTTPS, idêntica à da Meta), `THREADS_GRAPH_VERSION` (`v1.0`),
`THREADS_REFRESH_WINDOW_DAYS` (`30`) e `THREADS_CONTAINER_WAIT_SECONDS` (`20`). Sem as três primeiras o Threads fica
desabilitado e o Facebook não é afetado.

### Imagem no Threads: endereço público
A Threads API não recebe upload: a **Meta baixa a imagem de uma URL pública**. O Hub serve a imagem numa **URL temporária e assinada**
(`/publico/imagem.jpg?t=…`, validade de 30 min, só enquanto o envio ao Threads está em andamento, sem login, sem cache) e a entrega ao
Threads. Por isso o Hub precisa estar **alcançável pela internet em HTTPS** quando houver imagem para o Threads:
- `PUBLIC_BASE_URL` (ex.: `https://hub.exemplo.com`): endereço público HTTPS. Se vazio, usa a origem do `THREADS_REDIRECT_URI`.
  Sem endereço público HTTPS o formulário recusa imagem com Threads (texto e Facebook seguem normais).
- O host público precisa estar em `DJANGO_ALLOWED_HOSTS` e o proxy/túnel deve permitir `GET`/`HEAD` anônimos em `/publico/imagem.*`.
- Se a Meta não conseguir processar a imagem, o alvo do Threads **falha** (nunca vira só texto) e dá para **Tentar novamente**;
  cada nova tentativa gera uma URL nova. O Gunicorn registra só o caminho (sem a query com o token): `docker/gunicorn.conf.py`.
- Variáveis: `THREADS_IMAGE_URL_TTL_SECONDS` (`1800`), `THREADS_IMAGE_WAIT_SECONDS` (`60`) e `PUBLISH_REQUEST_BUDGET_SECONDS` (`150`, deve ficar
  abaixo do `--timeout` do Gunicorn). O tempo da requisição manda: alvos que não couberem ficam pendentes (**Continuar envio**).

### Desenvolvimento: túnel HTTPS
A Meta exige HTTPS no redirect do Threads, então em desenvolvimento use um túnel (exemplo sem instalar nada, com Docker):

```bash
docker run --rm --name social-hub-tunnel cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://host.docker.internal:8080
```

1. Anote a URL `https://….trycloudflare.com` impressa. **Ela muda a cada vez que o túnel sobe**: atualize a URL de callback na Meta
   **e** o `THREADS_REDIRECT_URI` no `.env` (`https://<url>/contas/threads/callback/`) e recrie o container (`docker compose up -d --force-recreate`).
2. No `.env`, só em desenvolvimento: `DJANGO_ALLOWED_HOSTS` com `.trycloudflare.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com`
   e `DJANGO_BEHIND_PROXY=true`.
3. **Acesse o Hub pela URL do túnel** (faça login nela) antes de clicar em *Conectar Threads*: o cookie de sessão é por endereço, e o Hub avisa
   se você iniciar por outro host.
4. Enquanto o túnel está aberto, o Hub fica **acessível pela internet**: use senha forte e feche o túnel ao terminar
   (`docker rm -f social-hub-tunnel`). Em produção use um domínio próprio com TLS.

### Tokens e limites
- O token do Threads vale **60 dias**. Ele é renovado **ao publicar ou ao Verificar** quando faltar menos de 30 dias; sem uso por mais de
  60 dias a conta passa a "Reconexão necessária" e basta **Reconectar**.
- Limite da Meta: 250 publicações por 24 h por perfil. Vídeo, carrossel e respostas no Threads ainda não existem.
- Os callbacks de **desinstalação** e **exclusão de dados** ainda não são tratados (exigidos para o modo Live da Meta).

## WhatsApp (Status) via Evolution API

Publica no **Status do WhatsApp** de um número **já pareado** na sua **Evolution API** (Baileys), junto ou separado de Facebook e Threads, no mesmo
formulário. Não há OAuth nem **QR** no Hub: o pareamento é feito na Evolution; o Hub só guarda o nome da instância e a chave dela.

> **Aviso:** o **Baileys não é oficial** (é o WhatsApp Web). Envio frequente ou em massa pode levar ao **banimento do número**. Use de forma manual e esporádica.
> O Status **não pode ser apagado** pelo Hub: teste com um número seu.

### Configurar
1. No `.env`, defina `EVOLUTION_API_URL` com a **origem HTTPS** da sua Evolution (só o host, ex.: `https://evolution.exemplo.com`; um caminho como `/manager` é ignorado)
   e reinicie o serviço. Sem ela a integração fica desligada (as outras plataformas seguem normais).
2. Em **Contas conectadas → Adicionar WhatsApp**, informe o **nome da instância** e a **chave da instância** (a chave da própria instância, **nunca a chave global** da Evolution).
   O Hub confere que a instância está conectada (`open`) e guarda a chave **cifrada**; ela não é exibida de novo.
3. Em **Nova publicação**, marque o grupo **Status do WhatsApp**. O texto vira o Status (ou a legenda da imagem) e a audiência é a de **todos os contatos** do número. Atenção: são os contatos que a **Evolution** conhece (com nome), que podem incluir pessoas fora da sua agenda; confira com `POST /chat/findContacts/{instância}` antes de publicar.

### Regras
- A imagem é **opcional** com WhatsApp (continua obrigatória com Página do Facebook). Ela vai **em base64** na chamada: **não** precisa de túnel nem de `PUBLIC_BASE_URL`.
- Se a instância cair ou a chave for recusada, a conta fica em **Reconexão necessária**: refaça o pareamento na Evolution e use **Atualizar chave** na tela de Contas.
- Outras falhas (rede, tempo esgotado, limite) deixam o alvo como **Falhou**, e **Tentar novamente** o reenvia. Se o Hub der **timeout**, a Evolution pode ter concluído o envio depois (observado com ~2265 contatos): **confira no celular antes de Tentar novamente**, ou o Status sai duplicado (limitação conhecida).
- O host da Evolution vem **só** do servidor; o usuário nunca informa endereço. Chave, imagem e texto não vão para logs.
- Variáveis: `EVOLUTION_API_URL` (HTTPS) e `EVOLUTION_TIMEOUT_SECONDS` (`120`; o tempo real é limitado pelo orçamento da requisição). Com muitos contatos a Evolution leva mais de 1 min para distribuir o Status.

## Publicação em segundo plano (worker)

Em produção o envio **não** acontece na requisição: *Publicar* cria os alvos na fila e responde na hora; um **worker** (container `worker`) os envia **um por vez**, na ordem de criação, e a página da publicação se atualiza sozinha (a cada 3 s, só enquanto há alvo na fila ou enviando).

```bash
docker compose up -d --build        # sobe web + worker
docker compose logs -f worker       # acompanha os envios (só ids, plataforma e estado; nunca texto ou chaves)
docker compose exec worker python manage.py worker_health   # 0 = ativo; 1 = parado (mostra a fila)
docker compose exec worker python manage.py run_worker --once   # um ciclo manual (manutenção)
```

- **Parar com segurança:** `docker compose stop worker` envia **SIGTERM**: o worker termina o alvo em andamento e sai (o compose espera até 150 s). Uma parada forçada deixa o alvo **Incerto**.
- **Worker parado:** os envios ficam na fila e o detalhe mostra "O envio em segundo plano não está ativo". Ao voltar, o worker retoma pela ordem de criação.
- **Incerto:** quando a plataforma pode ter publicado mas o Hub não sabe (resposta perdida depois de enviar, worker reiniciado no meio do envio, `sending` há mais de `PUBLISH_SENDING_STALE_SECONDS`), o alvo vira **Incerto** e **nunca** volta sozinho para a fila. Confira na plataforma e escolha **Já foi publicado** (marca como publicado, sem link) ou **Reenviar** (pode duplicar o post).
- **Tentar novamente** só reenfileira os alvos que **falharam** com certeza (recusa, reconexão necessária, conexão que nunca chegou ao servidor).
- **Modos (`PUBLISH_MODE`):** `worker` (padrão em produção) enfileira; `inline` (padrão em desenvolvimento e nos testes) envia na requisição, com lote, orçamento de tempo e **Continuar envio**. Para voltar ao modo antigo basta definir `PUBLISH_MODE=inline` (sem migração); alvos já na fila só são enviados com `inline` ao usar *Tentar novamente*/*Continuar envio* ou com o worker ativo.
- **Variáveis:** `PUBLISH_MODE`, `WORKER_POLL_SECONDS` (`2`: pausa sem fila), `WORKER_HEARTBEAT_STALE_SECONDS` (`180`: idade máxima da última batida para considerar o worker ativo) e `PUBLISH_SENDING_STALE_SECONDS` (`900`: tempo máximo de um alvo `sending` antes de virar Incerto).
- **Limitações:** um worker só (um Status de 100 s atrasa os seguintes) e ainda **não** há agendamento nem consulta à plataforma para resolver o Incerto sozinho. Decisão: [ADR-0011](docs/architecture/adr/0011-publicacao-em-segundo-plano-worker-no-banco-estado-incerto-e-recuperacao-sem-reenvio.md).

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | — | Obrigatória em produção |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts aceitos, separados por vírgula |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | vazio | Origens com esquema, ex.: `https://hub.exemplo.com` |
| `DJANGO_TIME_ZONE` | `America/Sao_Paulo` | Fuso horário |
| `DJANGO_SECURE_SSL` | `false` | Liga redirecionamento HTTPS, cookies seguros e HSTS |
| `DJANGO_BEHIND_PROXY` | `false` | Confia em `X-Forwarded-Proto` do proxy reverso |
| `DJANGO_SUPERUSER_*` | — | Admin criado no start se ainda não existir |
| `WEB_PORT` | `8000` | Porta publicada no host |
| `GUNICORN_WORKERS` | `2` | Workers do Gunicorn |
| `META_*` | — | Integração com o Facebook (veja a seção acima) |
| `THREADS_*` | — | Integração com o Threads (veja a seção acima) |
| `EVOLUTION_*` | — | WhatsApp (Status) via Evolution API: `EVOLUTION_API_URL` (HTTPS) e `EVOLUTION_TIMEOUT_SECONDS` (`120`) |
| `PUBLISH_BATCH_SIZE` | `5` | Teto de alvos enviados por requisição de publicação (modo `inline`) |
| `PUBLISH_MODE` | `worker` (prod) · `inline` (dev) | Onde o envio acontece: `worker` (segundo plano) ou `inline` (na requisição) |
| `WORKER_POLL_SECONDS` · `WORKER_HEARTBEAT_STALE_SECONDS` · `PUBLISH_SENDING_STALE_SECONDS` | `2` · `180` · `900` | Pausa do worker sem fila; idade máxima da batida do worker; prazo de um alvo `sending` antes de virar Incerto |
| `PUBLIC_BASE_URL` | — | Endereço público HTTPS do Hub (imagem no Threads); vazio = origem do redirect do Threads |
| `PUBLISH_REQUEST_BUDGET_SECONDS` | `150` | Orçamento de tempo de uma requisição de envio |
| `THREADS_IMAGE_*` | — | Validade da URL (`..._URL_TTL_SECONDS`) e espera do container (`..._WAIT_SECONDS`) |
| `MEDIA_ROOT` | `/media` (Docker) | Pasta das imagens de publicação |

## Manutenção

**Backup do SQLite** (consistente, mesmo com o app rodando):

```bash
docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/db.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d)"
docker compose cp web:/data/backup.sqlite3 ./backup.sqlite3
```

**Atualizar** após novas alterações: `git pull && docker compose up --build -d` (as migrations rodam no start).

**Novas migrations:** `docker compose exec web python manage.py makemigrations` e commit dos arquivos gerados.

**Atualizar dependências:** edite `requirements.txt` / `package.json` e reconstrua a imagem.

## Segurança básica

- `DEBUG` sempre desligado em produção; `SECRET_KEY` obrigatória e validada.
- Container executa como usuário sem privilégios; `.env` fora da imagem (`.dockerignore`) e do git.
- Cookies `HttpOnly`, CSRF ativo, `X-Frame-Options: DENY`, `nosniff`; com HTTPS: cookies seguros e HSTS.
- Ainda **não** há limitação de tentativas de login — considere adicionar (ex.: django-axes) antes de expor publicamente.
- Sirva atrás de um proxy reverso com TLS em produção e ative `DJANGO_SECURE_SSL=true`.

## Próximas etapas

Agendamento (a fila/worker já existe: falta `scheduled_at` e a tela Agenda), insights reais na dashboard e Instagram — todos no app `social`. Para o WhatsApp: grupos/contatos, vídeo e lista de contatos do Status.
