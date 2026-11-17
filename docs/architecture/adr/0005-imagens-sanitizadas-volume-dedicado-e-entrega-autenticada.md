---
name: ADR-0005
description: Imagens de publicação sanitizadas com Pillow, em volume dedicado, entregues por view autenticada.
alwaysApply: false
---

# ADR-0005: Imagens sanitizadas, em volume dedicado e entregues por view autenticada

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A feature `0003-publicar-no-facebook` recebe uploads de usuários e os envia à Meta. Uploads são vetor de ataque
(arquivo falso, *polyglot*, bomba de descompressão) e imagens de celular carregam metadados sensíveis (EXIF/GPS). O
histórico precisa exibir miniaturas, mas as imagens são privadas até serem publicadas.

## Decisão
- Toda imagem é **validada e re-encodada com Pillow** (JPEG ou PNG): formato real verificado, limites de **bytes** (8 MiB)
  e **pixels** (40 MP), **EXIF removido**, nome de arquivo **aleatório** (o nome original é descartado).
- As imagens ficam em **volume Docker dedicado** (`media_data:/media`), fora do código e do banco.
- O arquivo vai à Meta por **upload multipart**; **não** há URL pública nem `MEDIA_URL`.
- O Hub exibe a imagem por uma **view autenticada** (`/publicacoes/<id>/imagem/`) que só serve ao dono (404 aos demais).
- Alternativas descartadas: guardar o arquivo **como veio** (vaza EXIF, aceita conteúdo não validado), **MEDIA_URL público**
  (imagens acessíveis sem login), **imagem por URL pública** para a Meta (exige expor mídia e domínio HTTPS) e **S3**
  (dependência e credenciais desproporcionais agora).

## Consequências
- **+** Privacidade (sem GPS, sem acesso anônimo) e defesa contra arquivos maliciosos.
- **+** Sem dependência externa de armazenamento.
- **−** Dependência do Pillow; o arquivo enviado difere do original (re-encode).
- **−** O histórico depende do volume `/media`: exige backup; perdê-lo afeta miniaturas, não os posts já publicados.
- **−** Imagens passam pelo Django (aceitável neste volume de uso); sem limpeza automática de imagens antigas.
