# Social Hub

Plataforma web para centralizar a publicação em redes sociais: **Facebook** (Páginas), **Instagram** (via Página),
**Threads** e **Status do WhatsApp** (via Evolution API), com geração de imagem e texto por IA (Gemini/DeepSeek).

> Agendamento e insights reais **ainda não** existem; a dashboard usa dados demonstrativos.
> Detalhes de cada funcionalidade: `specs/NNNN-*/spec.md`. Decisões: `docs/architecture/adr/`. Estado atual: `docs/STATE.md`.

## Stack

Python 3.13 + Django 5.2 LTS · Django Templates + Tailwind 3 + ilhas React/MUI (ADR-0015) · SQLite (WAL) ·
Gunicorn + WhiteNoise · Docker Compose (`web` + `worker`).

## Rodando

**Docker (recomendado)**

```bash
cp .env.example .env        # edite: DJANGO_SECRET_KEY (≥ 32 chars), DJANGO_SUPERUSER_*, hosts
docker compose up --build -d
```

Acesse `http://localhost:8000` (ou `WEB_PORT`). As migrations e o admin inicial rodam no start.
O código vai na imagem: depois de alterar, rode `docker compose up -d --build` de novo.

**Local (sem Docker)** — Python 3.13+ e Node 22+:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install && npm run build      # CSS, vendors e bundle MUI em static/dist
cp .env.example .env && python manage.py migrate && python manage.py runserver
```

**Testes:** `python manage.py test apps` · **Esteira SDD:** `node scripts/audit-esteira.mjs .`,
`node scripts/validate-mermaid.mjs .` e `node scripts/eval-spec-fidelity.mjs .` (os mesmos gates do CI em `.github/workflows/esteira.yml`).

## Estrutura

```
config/settings/     base · dev · prod
apps/core/           healthcheck, navegação
apps/accounts/       cadastro, login por e-mail, recuperação de senha, perfil
apps/dashboard/      dashboard (dados demonstrativos)
apps/social/         contas, OAuth, clientes Graph/Threads/Evolution/IA, publicações, worker
templates/ frontend/ static/js/   interface (Tailwind + MUI)
specs/ docs/         especificações (SDD), ADRs, glossário, STATE
```

## Contas e segurança de acesso

- Tudo exige login (`LoginRequiredMiddleware`); só login, cadastro, recuperação de senha, termos, privacidade e `/healthz/` são públicos.
- **Cadastro** (0013/0015): e-mail único (minúsculas) e senha forte. **Login** (0014, ADR-0016): só por e-mail, 5 falhas por e-mail ou 20 por IP em 15 min → 429.
- **Recuperação de senha** (0016, ADR-0017): link de uso único de 30 min. Configure `EMAIL_*` e `DEFAULT_FROM_EMAIL`; sem SMTP os e-mails vão para `var/emails/`. Os links usam `PUBLIC_BASE_URL`.

## Integrações

Todas são opcionais: sem as variáveis, a rede aparece como "Integração … não configurada" e o resto segue normal.
Conecte e gerencie em **Contas conectadas** (`/contas/`, central com ícones + painel da rede, spec 0017).
Tokens e chaves ficam **cifrados** com Fernet (`META_TOKEN_ENCRYPTION_KEY`, ADR-0002) e nunca vão para log ou HTML.

| Rede | Variáveis | Configuração na Meta / serviço | Spec · ADR |
| --- | --- | --- | --- |
| Facebook (Páginas) | `META_APP_ID`, `META_APP_SECRET`, `META_LOGIN_CONFIG_ID`, `META_REDIRECT_URI`, `META_GRAPH_VERSION` (`v27.0`), `META_TOKEN_ENCRYPTION_KEY` | App com "Gerenciar tudo na sua Página"; permissões `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `read_insights`; redirect cadastrado e ID da configuração do Login para Empresas | 0002, 0003 · ADR-0003 |
| Instagram | as da Meta + `INSTAGRAM_CONTAINER_WAIT_SECONDS` | Conta profissional vinculada à Página; `instagram_basic` + `instagram_content_publish` na mesma configuração; **reconecte a Página** | 0009 · ADR-0013 |
| Threads | `THREADS_APP_ID`, `THREADS_APP_SECRET`, `THREADS_REDIRECT_URI` (HTTPS), `THREADS_GRAPH_VERSION` (`v1.0`) | Caso de uso "Acessar a API do Threads" com `threads_basic`, `threads_content_publish`, `threads_delete`; testador convidado e perfil público | 0004, 0005 · ADR-0006 |
| WhatsApp (Status) | `EVOLUTION_API_URL`, `EVOLUTION_TIMEOUT_SECONDS` | Veja a seção abaixo | 0006 · ADR-0010 |
| IA (imagem e texto) | `GEMINI_IMAGE_MODELS`, `GEMINI_TEXT_MODEL`, `DEEPSEEK_TEXT_MODEL`; `GEMINI_API_KEY`/`DEEPSEEK_API_KEY` só como fallback | Cada usuário cadastra a própria chave na tela de nova publicação | 0008 · ADR-0012 |

Gere a chave Fernet com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Para rotacionar, use `NOVA,ANTIGA` até regravar as contas. **Faça backup dela fora do repositório**: sem ela, é preciso reconectar tudo.

**Endereço público (Threads e Instagram com imagem):** a Meta baixa a imagem de uma URL temporária e assinada
(`/publico/…`, ADR-0008). O Hub precisa estar em HTTPS público: `PUBLIC_BASE_URL` (vazio = origem do `THREADS_REDIRECT_URI`).
Em desenvolvimento, use um túnel e atualize a URL na Meta e no `.env` a cada vez que ele subir:

```bash
docker run --rm --name social-hub-tunnel cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://host.docker.internal:8080
```

Com o túnel, defina `DJANGO_ALLOWED_HOSTS=.trycloudflare.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com` e
`DJANGO_BEHIND_PROXY=true`, faça login **pela URL do túnel** e feche-o ao terminar (`docker rm -f social-hub-tunnel`).

**Limites e cuidados:** a publicação é **real**, então teste em Páginas/perfis de teste. O token do Threads vale 60 dias e é renovado
ao publicar ou atualizar. O Instagram aceita proporção 4:5–1,91:1 e até 2.200 caracteres.

## WhatsApp (Status) via Evolution API

Publica no Status de um número **já pareado** na sua Evolution API. O pareamento (QR) é feito na Evolution, não no Hub.
- `EVOLUTION_API_URL`: só a origem HTTPS (ex.: `https://evolution.exemplo.com`). `EVOLUTION_TIMEOUT_SECONDS` vale `120` por padrão.
- Em Contas conectadas, informe o nome e a **chave da instância**, nunca a chave global da Evolution. Ela é guardada cifrada.
- O Status vai para **todos os contatos** que a Evolution conhece. A imagem segue em base64, sem túnel.
- **Aviso:** o Baileys não é oficial, e envio frequente ou em massa pode levar ao **banimento** do número. O Status não pode ser apagado pelo Hub.
  Em timeout, confira no celular antes de *Tentar novamente* para não duplicar.

## Publicações (texto + imagem em várias Páginas)

Em **Publicações → Nova publicação**: texto, uma imagem (JPEG/PNG até 8 MB, re-encodada sem metadados) e uma ou várias contas
de qualquer rede no mesmo formulário (ADR-0007). O resultado sai **por destino**, com **Tentar novamente** só nos que falharam.

- Em produção, *Publicar* só enfileira e o worker envia (seção abaixo). Lote, orçamento de tempo e *Continuar envio* valem só no modo `inline`.
- **Excluir** (spec 0010, ADR-0014): *Remover do Hub* apaga só o histórico. *Apagar na plataforma* funciona no Facebook e no
  Threads (Threads exige `threads_delete` e reconexão).

## Publicação em segundo plano (worker)

O container `worker` (`python manage.py run_worker`, spec 0007, ADR-0011) envia **um destino por vez**, na ordem de criação.
`PUBLISH_MODE` escolhe entre `worker` (padrão em produção) e `inline` (envio na requisição, padrão em dev e testes).

- **Incerto:** se a plataforma pode ter publicado mas o Hub não sabe, o destino nunca volta sozinho à fila. Confira e escolha
  *Já foi publicado* ou *Reenviar*, que pode duplicar o post.
- **Parar com segurança:** `docker compose stop worker` envia SIGTERM. O worker termina o destino atual e sai.
- Ajustes: `WORKER_POLL_SECONDS`, `WORKER_HEARTBEAT_STALE_SECONDS` e `PUBLISH_SENDING_STALE_SECONDS` (tabela abaixo).

```bash
docker compose logs -f worker                                  # envios (só ids e estados)
docker compose exec worker python manage.py worker_health      # 0 = ativo
```

## Configuração geral

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | — | Obrigatória em produção |
| `DJANGO_ALLOWED_HOSTS` · `DJANGO_CSRF_TRUSTED_ORIGINS` | `localhost,127.0.0.1` · vazio | Hosts e origens aceitos |
| `DJANGO_SECURE_SSL` · `DJANGO_BEHIND_PROXY` | `false` | HTTPS/HSTS/cookies seguros · confiar no `X-Forwarded-Proto` |
| `DJANGO_TIME_ZONE` | `America/Sao_Paulo` | Fuso horário |
| `DJANGO_SUPERUSER_*` | — | Admin criado no start (entra pelo e-mail) |
| `WEB_PORT` · `GUNICORN_WORKERS` | `8000` · `2` | Porta no host · workers do Gunicorn (`--timeout 180`) |
| `PUBLISH_MODE` | `worker` (prod) · `inline` (dev) | Onde o envio acontece |
| `PUBLISH_BATCH_SIZE` · `PUBLISH_REQUEST_BUDGET_SECONDS` | `5` · `150` | Lote e orçamento de tempo no modo `inline` |
| `WORKER_POLL_SECONDS` · `WORKER_HEARTBEAT_STALE_SECONDS` · `PUBLISH_SENDING_STALE_SECONDS` | `2` · `180` · `900` | Pausa do worker · batida máxima · prazo antes de virar Incerto |
| `THREADS_IMAGE_URL_TTL_SECONDS` · `THREADS_IMAGE_WAIT_SECONDS` | `1800` · `60` | URL pública da imagem · espera do container |
| `META_*` · `THREADS_*` · `EVOLUTION_*` · `GEMINI_*` · `DEEPSEEK_*` | — | Integrações (seção acima) |
| `MEDIA_ROOT` | `/media` (Docker) | Imagens das publicações (volume `media_data`) |

## Operação

- **Backup do banco** (com o app rodando):
  `docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/db.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d)"`
  e depois `docker compose cp web:/data/backup.sqlite3 ./backup.sqlite3`. Faça backup também do volume `media_data` e da chave Fernet.
- **Atualizar:** `git pull && docker compose up --build -d`. `docker compose down -v` **apaga** o banco.
- **Produção:** proxy reverso com TLS, `DJANGO_SECURE_SSL=true` e redirects HTTPS na Meta. O container roda sem privilégios e o `.env` fica fora da imagem e do git.

## Próximas etapas

Agendamento (a fila já existe), insights reais na dashboard, Stories/carrossel no Instagram, seguidores do Threads
(`threads_manage_insights`) e callbacks de desinstalação/exclusão de dados da Meta antes do modo Live.
