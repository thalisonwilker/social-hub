---
name: TESTING
description: Comandos de gate e convenções de teste. Puxe ao codar, validar ou montar CI.
alwaysApply: false
---

# TESTING — Como verificar o projeto

> **Fonte única dos comandos de gate** e das convenções de teste. É o que o **DoD**, a **CI** e os
> **subagentes** consomem para provar que uma task/feature está pronta — sem inspeção visual.
> Preenchido no kickoff (eixo Qualidade) e mantido vivo.

## Como rodar
| Nível         | Comando                   | Quando |
|---------------|---------------------------|--------|
| Unidade       | `docker compose run --rm --build web python manage.py test apps` | sempre; rápido, sem rede (Graph API mockada) |
| Integração    | `docker compose run --rm --build web python manage.py test apps.social.tests.test_facebook_connect` | serviços com banco e sessão reais |
| Aceite (UAT)  | `docker compose run --rm --build web python manage.py test apps.social` | um teste `test_AC_N_*` por critério da spec |
| Lint / format    | _(não configurado)_       | pendência: adotar ruff |
| Análise estática | `python manage.py check` · `python manage.py makemigrations --check --dry-run` | CI — sem findings bloqueantes (SAST pendente) |
| Cobertura        | _(não configurado)_       | pendência: `coverage` com mínimo definido |

## Convenções
- Pirâmide: muitos testes de unidade, menos de integração, poucos de aceite.
- **Cada `AC-N` da spec tem um teste de aceite que é o seu gate.** Nomeie o teste com o ID
  (`test_AC_1_*` / `AC-1: ...`) para rastreabilidade spec → teste.
- Domínio não sobe infra; integração usa `<testcontainer / mock de borda>`.
- **Análise estática** (escolha por stack): type-check (`<mypy/tsc/…>`), complexidade/smells e
  **SAST/segurança** (`<sonar/codeql/semgrep/…>`). Define o que é **bloqueante** (barra o merge)
  vs **aviso** (entra como tendência em `metrics.md`, não bloqueia).

## Gates (Definition of Done executável)
- Uma **task** só vira `done` quando o **Gate (comando)** dela em `tasks.md` passa.
- Uma **feature** só faz merge quando todos os AC estão verdes + lint + **análise estática limpa**
  (sem findings bloqueantes) + cobertura mínima.
- A **CI roda exatamente estes comandos** — falhar bloqueia o merge.

## Ambiente local sem Docker (iteração rápida)
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py test apps          # usa config.settings.dev
```
Os testes não acessam a rede: a Graph API é sempre mockada (`apps/social/tests/helpers.py`); a Threads API também é sempre mockada (`threads_helpers.py`, `threads_publisher.py`); as imagens de teste são geradas
com Pillow em memória e gravadas em diretório temporário (`publication_helpers.py`). O gate oficial roda no
container, que reproduz o ambiente de produção.

## O que a CI executa
<Pipeline em ordem: lint → análise estática → unidade → integração → aceite → cobertura (relatório).
Mais a regra SDD: falhar PR que altera código sem spec aprovada.
**Cobertura e análise estática são publicadas como artefatos do PR** — evidência rastreável do
resultado de qualidade, que o `/metricas` consome para a tendência.>
