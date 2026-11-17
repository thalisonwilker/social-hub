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
- 2026-11-17 · Threads/publicação · O Threads só recebe TEXTO nesta etapa (imagem é non-goal da 0004): num post misto a imagem vai só ao Facebook, como a spec manda · imagem no Threads exige URL pública (feature futura).
- 2026-11-17 · testes Django · Nomear um helper de `client` em um TestCase sobrescreve `self.client` e quebra tudo · usar nomes como `fake_client`.
- 2026-11-17 · testes/mídia · Teste que grava arquivo sem `MEDIA_ROOT` temporário suja o volume real (já aconteceu na 0003) · todo teste de mídia usa diretório temporário; conferir `find media -type f` após rodar a suíte.
- 2026-11-17 · Docker/túnel · O túnel (`docker run --rm`) morre se o Docker Desktop parar, e o container do Hub volta sozinho mas o túnel não · reiniciar o túnel e atualizar a URL na Meta/`.env`.

## Promovidas (histórico curto)
> Rastro de para onde foram as lições podadas — só o link, sem reexplicar. Poda este histórico também.
- <YYYY-MM-DD: "<lição>" → [ADR-NNNN](architecture/adr/NNNN-*.md) / glossary / CLAUDE.md>
