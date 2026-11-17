---
name: lessons
description: Aprendizados transversais e gotchas descobertos durante o trabalho — quirks de lib, armadilhas de setup, suposições que se provaram erradas. Área de staging volátil que se auto-poda (o que estabiliza vira ADR/glossary/CLAUDE.md/TESTING e sai daqui). Puxe quando for mexer numa área com histórico de armadilha, ou antes de tomar uma decisão que já esbarrou num gotcha registrado.
alwaysApply: false
---

# LESSONS — Aprendizados & gotchas

> **Área de staging, não cemitério.** Registra o que se aprende na marra: quirks de biblioteca,
> armadilhas de ambiente, suposições que quebraram. É **volátil** — diferente do **ADR** (decisão
> durável) e do **STATE** (o que estamos fazendo agora). A lição que **estabiliza** é **promovida**
> e **removida** daqui (ver poda abaixo). Se este arquivo cresce sem parar, a poda não está rolando.

## Como usar
- **Captura inline (na hora):** ao corrigir um erro não-óbvio, quebrar uma suposição ou descobrir
  um gotcha, adicione **1 linha aqui na hora** — não espere o handoff (o detalhe some).
- **Consolidação (no `/handoff`):** ao pausar, revise as lições da sessão: alguma duplicada?
  alguma já estabilizou → **promova e remova**.

### Poda — para onde a lição vai quando amadurece
| A lição virou… | Vai para | Sai daqui |
|---|---|---|
| Decisão difícil de reverter | ADR (`docs/architecture/adr/`) | ✅ |
| Termo/conceito de negócio | `docs/glossary.md` | ✅ |
| Convenção de código/agente | `CLAUDE.md` | ✅ |
| Padrão de teste/quality gate | `docs/engineering/TESTING.md` | ✅ |
| Gotcha que ainda não estabilizou | **fica aqui** | — |

## Aprendizados ativos
> Formato: `- <YYYY-MM-DD> · <área/arquivo> · o gotcha em 1 linha · como evitar/mitigar`.
> Mantenha acionável e curto. Se não é acionável, não é uma lição — é desabafo.

- 2026-11-17 · Meta/Threads · A URL de redirect cadastrada precisa ser IDÊNTICA à enviada (inclui caminho e barra final); só a raiz do túnel dá erro 1349168 "URL bloqueada" · cadastrar `…/contas/threads/callback/` completa.
- 2026-11-17 · Meta/Threads · Erro 1349245 "usuário não aceitou o convite para testar o app" = o perfil precisa ser Testador do Threads, aceitar o convite no Threads (Permissões de sites → Convites) e o perfil deve estar PÚBLICO · conferir antes de conectar.
- 2026-11-17 · Meta/Threads · Redirect HTTPS é obrigatório mesmo em desenvolvimento, e as URLs de desinstalação/exclusão também exigem HTTPS (deixe vazias) · usar túnel HTTPS; a URL do túnel muda a cada subida (atualizar Meta + `.env`).
- 2026-11-17 · Threads/publicação · Container de TEXTO ficou `FINISHED` em ~220 ms (observado no UAT); a "espera de 30 s" da doc não se aplicou · seguir consultando o status em vez de esperar tempo fixo.
- 2026-11-17 · Threads/imagem · A Threads API não aceita upload: a Meta baixa a imagem de uma URL pública (0005 serve uma URL assinada e temporária pelo Hub) · o Hub precisa estar alcançável em HTTPS (túnel/domínio) para publicar imagem no Threads.
- 2026-11-17 · testes/mock · `mock.patch(..., autospec=True)` não pode ser aninhado sobre o mesmo alvo (InvalidSpecError) · variar a resposta por estado no fake (ex.: `self.container_status`), não com um segundo patch.
- 2026-11-17 · testes/tempo · Argumentos padrão `sleep=time.sleep` ficam presos na definição e um patch de `time.sleep` não os afeta (teste dormia 60 s de verdade) · resolver no corpo (`sleep or time.sleep`) e patchar o módulo `time` do serviço.
- 2026-11-17 · testes Django · Nomear um helper de `client` em um TestCase sobrescreve `self.client` e quebra tudo · usar nomes como `fake_client`.
- 2026-11-17 · testes/mídia · Teste que grava arquivo sem `MEDIA_ROOT` temporário suja o volume real (já aconteceu na 0003) · todo teste de mídia usa diretório temporário; conferir `find media -type f` após rodar a suíte.
- 2026-11-17 · Docker/túnel · O túnel (`docker run --rm`) morre se o Docker Desktop parar, e o container do Hub volta sozinho mas o túnel não · reiniciar o túnel e atualizar a URL na Meta/`.env`.

- 2026-11-17 · Threads/imagem · A Meta baixa a imagem DURANTE a criação do container (POST fica ~4 s aberto; UA `facebookexternalhit`, só GET) e o container de imagem ficou `FINISHED` em ~3,7 s · o Gunicorn precisa de ≥ 2 workers (um espera a Meta, o outro serve a imagem).
- 2026-11-17 · Threads/túnel · Com o hostname do túnel recém-criado (~2 min) a 1ª criação de container de imagem falhou (`code=1 subcode=2207052`); reenviar funcionou · depois de subir um túnel, esperar alguns minutos antes de publicar imagem.

- 2026-11-17 · Evolution/doc · As páginas oficiais da referência da Evolution (doc.evolution-api.com, mintlify) deram 404/410 e as fontes secundárias divergem (corpo plano × `statusMessage`; base64 com/sem `data:`) · o corpo do Status ficou isolado em `EvolutionClient._status_body`/`_extract_*` e é fixado no UAT contra a instância real.
- 2026-11-17 · testes Django · Um helper chamado `publish` num TestCase com `PublicationTestMixin` é sombreado pelo mock `self.publish` (instância) e chama o Graph sem querer · nomear `do_publish`.
- 2026-11-17 · WhatsApp/Baileys · Não é oficial: envio frequente pode banir o número, e o Status não é apagável pelo Hub · testar com número próprio e uso manual/esporádico.
- 2026-11-17 · testes/Docker · O `.dockerignore` exclui `README.md` (e `Dockerfile`) da imagem: testes que leem esses arquivos quebram no gate do container · usar `unittest.skipUnless(arquivo.exists())` (rodam localmente, pulam no container).
- 2026-11-17 · Evolution 2.3.7/Status · `content` de imagem é repassado como `image.url`: base64 PURO é lido como caminho de arquivo (`ENAMETOOLONG ... open '/9j/4AAQ...'` no log da Evolution) · enviar como data URI (`data:image/jpeg;base64,...`); o corpo de texto exige `backgroundColor` e `font`.
- 2026-11-17 · Evolution/log · O log da própria Evolution (container dela) mostra o motivo real de um Status recusado; o Hub não loga o corpo da resposta de propósito · para depurar o contrato, rode `scripts/uat_evolution.py` e olhe o log da Evolution.

## Promovidas (histórico curto)
> Rastro de para onde foram as lições podadas — só o link, sem reexplicar. Poda este histórico também.
- <YYYY-MM-DD: "<lição>" → [ADR-NNNN](architecture/adr/NNNN-*.md) / glossary / CLAUDE.md>
