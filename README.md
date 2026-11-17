# Social Hub

Plataforma web para centralizar o gerenciamento e a publicação de conteúdos em redes sociais (Facebook, Instagram e Threads).

> **Estado atual (etapa 1):** estrutura base, autenticação, dashboard com dados **demonstrativos** e infraestrutura Docker.
> Integrações com a Meta, publicação e agendamento **ainda não** foram implementadas.

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
  social/               Reservado para as integrações (contas, publicações, agenda)
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

Modelos de contas/publicações, OAuth e Graph API da Meta, publicação, agendamento e fila (a definir) — todos no app `social`.
