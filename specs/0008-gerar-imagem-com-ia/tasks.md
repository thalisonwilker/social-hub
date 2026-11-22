---
name: tasks
description: Decomposição e gates da feature 0008 (gerar imagem e texto com IA). Registro retroativo. Puxe ao revisar a feature.
alwaysApply: false
---

# Tasks — Gerar imagem com IA na postagem

> **Registro retroativo (2026-11-21).** A 0008 foi entregue no commit `d0c3575` sem `tasks.md`, e a
> rastreabilidade AC→task quebrou o gate `eval-spec-fidelity` da esteira. A tabela abaixo reconstrói a
> decomposição a partir do que foi entregue. Os testes ficam em `apps/social/tests/test_gemini_image.py`,
> um `test_AC_N_*` por critério. Gate geral: `.venv/bin/python manage.py test apps`.

## Plano
| # | Task | Cobre AC | Depende de | Gate (comando) | Status |
|---|------|----------|------------|----------------|--------|
| 1 | Modelos `AiProviderKey` (chave cifrada por usuário e provedor, ADR-0002) e `GeneratedImage` (temporária, do dono) + migração `0006_gemini_image_generation` | AC-3, AC-4, AC-7, AC-9 | — | `manage.py makemigrations --check` | done |
| 2 | Configuração: `GEMINI_API_KEY`, `GEMINI_IMAGE_MODELS` (o primeiro é o padrão), modelos de texto e `DEEPSEEK_TEXT_MODEL`; `.env.example` | AC-4, AC-8, AC-9 | — | `manage.py test apps.social.tests.test_gemini_image` | done |
| 3 | `services/gemini.py`: cliente de imagem e texto com host fixo, erros por categoria e sanitizados (sem chave nem prompt no log); imagem passa por `sanitize_image` | AC-2, AC-5, AC-6, AC-7, AC-9 | 2 | idem | done |
| 4 | `services/deepseek.py`: segundo provedor de texto com a mesma regra de erros | AC-6, AC-9 | 2 | idem | done |
| 5 | `views_ai.py` + rotas: gerar imagem, gerar texto, salvar, testar e remover chave, servir a imagem só ao dono; login e CSRF | AC-2, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9 | 1, 3, 4 | idem | done |
| 6 | Formulário de publicação: a imagem gerada vira a da publicação, o arquivo escolhido vence, "Descartar" | AC-3 | 1, 5 | idem | done |
| 7 | Templates `post_form.html`/`post_detail.html` e `static/js/ai-image.js`: seção "Criar imagem" (prompt, modelo, prévia), painel de texto ao lado do Texto, confirmação antes de substituir | AC-1, AC-3, AC-9 | 5, 6 | idem + UAT | done |
| 8 | Docs vivas: ADR-0012, glossário (Imagem gerada), STATE | — | 1–7 | revisão | done |

## Plano de teste
- Aceite (`test_gemini_image.py`): um `test_AC_N_*` por AC; o AC-9 cobre os dois provedores (Gemini e DeepSeek).
- Segurança: chave nunca reexibida nem logada (AC-4, AC-6), isolamento entre usuários e CSRF (AC-7).
- UAT: geração real com chave do Gemini e conferência dos IDs de `GEMINI_IMAGE_MODELS` (pendente no STATE).

## Divergências (SPEC_DEVIATION)
- [x] AC-9 (texto com IA) foi adicionado depois da aprovação do design. A spec já o marca assim, e nada fica pendente.

## Checklist de Definition of Done
- [x] Todos os AC verdes pelo gate executável
- [x] ADR registrado (ADR-0012)
- [x] Glossário atualizado (Imagem gerada)
- [ ] UAT com chave real do Gemini (ver `docs/STATE.md`)
