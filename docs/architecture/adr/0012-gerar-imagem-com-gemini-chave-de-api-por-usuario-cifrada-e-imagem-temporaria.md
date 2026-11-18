---
name: ADR-0012
description: Gerar imagem com IA (Gemini) — chave de API por usuário cifrada, host fixo, modelos em configuração e imagem gerada temporária sanitizada.
alwaysApply: false
---

# ADR-0012: Gerar imagem com Gemini — chave por usuário cifrada e imagem temporária

- **Status:** aceito · **Data:** 2026-11-17 · **Decisores:** Thalyson

## Contexto
A tela de nova publicação passa a gerar imagem por IA (spec 0008). Isso exige guardar um segredo de terceiros do usuário e chamar um serviço externo.

## Decisão
- A chave do Gemini é **por usuário** (`AiProviderKey`), cifrada com o mesmo Fernet do [ADR-0002](0002-tokens-de-pagina-criptografados-com-fernet.md); nunca é devolvida (só os 4 últimos caracteres), nem vai a log/URL/HTML. `GEMINI_API_KEY` do servidor é só fallback.
- O host do Gemini é fixo no código; o modelo só vale se estiver em `GEMINI_IMAGE_MODELS` (IDs mudam: ficam em configuração, o primeiro é o padrão).
- A imagem gerada é **sanitizada** (ADR-0005) e guardada como `GeneratedImage` temporária (24 h, dono único); o formulário recebe só o id e a sanitiza de novo ao publicar. Arquivo escolhido vence a gerada.
- Geração síncrona na requisição (timeout 90 s), sem SDK do Google (só `requests`).
- Alternativas descartadas: gerar no POST de publicar (sem pré-visualização), base64 no formulário, SDK `google-genai`.

## Consequências
- Cada usuário paga o próprio uso; o Hub não guarda prompt.
- Perder `META_TOKEN_ENCRYPTION_KEY` também invalida as chaves de IA (o usuário recadastra).
- Outros provedores cabem em `AiProviderKey.provider` + um novo cliente.
