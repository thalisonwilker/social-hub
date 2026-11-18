---
name: design
description: Design da feature 0008 — gerar imagem com Gemini, chave de API por usuário cifrada, imagem temporária e integração ao formulário de publicação.
alwaysApply: false
---

# Design — Gerar imagem com IA

> **Tier:** arquitetural (integração externa + segredo do usuário) · **Status:** aprovado · **Data:** 2026-11-17

## Contexto
`PublicationForm` recebe `image` (arquivo) e a sanitiza (`images.sanitize_image`, ADR-0005). Segredos já são cifrados com Fernet (`crypto.py`, ADR-0002); o cadastro da chave da Evolution (0006) é o precedente.

## Goals / Non-goals
- Goals: gerar imagem sem sair do formulário; reaproveitar sanitização e limites; chave nunca vaza.
- Non-goals: ver "Fora de escopo" da spec.

## Design proposto
- **Modelo `AiProviderKey`** (`owner`, `provider="gemini"`, `api_key_enc`, `last4`, timestamps; único por owner+provider). Cifra via `encrypt_token`.
- **Modelo `GeneratedImage`** (`owner`, `file`, `content_type`, `created_at`): imagem **já sanitizada**, em `/media`, entregue por view autenticada (padrão ADR-0005). Expira em 24 h; limpeza oportunista a cada geração.
- **Cliente** `services/gemini.py` (camada anticorrupção, como `evolution.py`): `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` com header `x-goog-api-key`, corpo `contents` + `generationConfig.responseModalities=["TEXT","IMAGE"]`; lê `inlineData` (base64). Host fixo; `model` validado contra `GEMINI_IMAGE_MODELS`; chave só no header; erros mapeados em códigos (`auth`, `quota`, `blocked`, `timeout`, `bad_response`, `network`).
- **Endpoints** (login + CSRF + só dono), JSON mínimo: `POST publicacoes/imagem-ia/gerar/` (prompt, modelo → `{id, url}`), `POST .../chave/` e `POST .../chave/remover/`, `GET .../imagem-ia/<id>/` (arquivo).
- **Integração ao formulário**: campo oculto `generated_image` (id). Em `PublicationForm.clean`: se não há upload e há `generated_image` do próprio usuário e não expirada, usa o arquivo como `upload` (passa de novo por `sanitize_image` — defesa em profundidade). Upload escolhido vence.
- **UI**: seção "Criar imagem" no `post_form.html`, grid 2 colunas (prompt + modelo + chave à esquerda; pré-visualização à direita; empilha no mobile). JS em `static/js/` usa `fetch` com CSRF; botão desabilita durante a chamada; "Descartar" limpa o campo oculto.

## 5 eixos
1. **Stack:** só `requests` (já presente). Sem SDK do Google.
2. **Arquitetura:** `interfaces` (views) → `services/gemini.py` → modelos; sem acoplar ao despacho de publicação (a imagem vira a `image` normal).
3. **Infra:** volume `/media` existente; nova env `GEMINI_API_KEY` (opcional), `GEMINI_IMAGE_MODELS`, `GEMINI_TIMEOUT_SECONDS` (padrão 90). Reversão: desligar a seção se `GEMINI_IMAGE_MODELS` vazio.
4. **Qualidade:** cliente com `requests` falso (sem rede nos testes); testes de segurança (segredo ausente de log/HTML/JSON), isolamento, expiração, precedência upload × gerada.
5. **Observabilidade:** log só com rótulo, modelo, status e código curto — nunca prompt, chave ou corpo.

## Alternativas
| Alternativa | Contras | Decisão |
|---|---|---|
| Gerar dentro do POST de publicar | prende a requisição, sem pré-visualização | descartada |
| Base64 no campo do formulário | payload grande, sem isolamento | descartada |
| **Endpoint JSON + imagem temporária + id oculto** | um pouco mais de código | **escolhida** |
| SDK `google-genai` | dependência nova sem ganho | descartada |

## Riscos
| Risco | Mitigação |
|---|---|
| IDs de modelo mudam/preview some | lista em config, não no código |
| Custo na chave do usuário | aviso na UI; sem retry automático |
| Chave vazar por log/erro | testes de segurança (AC-4/AC-6) |
| Geração lenta (>30 s) | timeout 90 s, botão com estado "Gerando…" |

## Questões em aberto
- [ ] (RESOLVIDO em 2026-11-17: padrões `gemini-nano-banana-2.1`, `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-2.5-flash-image`, conforme ai.google.dev/gemini-api/docs/image-generation; confirmar no UAT) **IDs de modelo:** a documentação consultada cita nomes divergentes (`gemini-3-pro-image-preview`, `gemini-nano-banana-2.1`). Preciso que você confirme quais usar como padrão e opções; até lá a lista fica em `GEMINI_IMAGE_MODELS`.
- [ ] Gerar de modo síncrono (previsto) é aceitável, ou prefere via worker?
