# Social Hub

Plataforma web para centralizar o gerenciamento e a publicação de conteúdos em redes sociais (Facebook, Instagram e Threads).

> **Estado atual:** estrutura base, autenticação, dashboard (dados **demonstrativos**), infraestrutura Docker e a
> **integração com Páginas do Facebook** (conectar, listar, verificar e desconectar).
> Publicação, agendamento e insights reais **ainda não** foram implementados.

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
  social/               Integração com a Meta: contas conectadas, OAuth, cliente Graph API, criptografia de tokens
templates/              layout.html (sidebar + header + conteúdo), partials, páginas
frontend/               Fonte do Tailwind (input.css, tailwind.config.js) e cópia de vendors
static/js/app.js        Tema claro/escuro, menu mobile e Lucide
static/dist/            Assets compilados (não versionado; gerado por `npm run build`)
docker/entrypoint.sh    migrate + criação do admin + start do Gunicorn
Dockerfile              Multi-stage: Node compila o frontend, Python executa o app
docker-compose.yml      Serviço web + volume `sqlite_data`
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

Insights reais na dashboard, publicação e agendamento, e as integrações com Instagram e Threads — todos no app `social`.
