---
name: tasks
description: Decomposição e gates da feature 0006 — Status do WhatsApp via Evolution API (conta = instância, envio único, base64, orçamento de tempo).
alwaysApply: false
---

# Tasks — WhatsApp: publicar no Status via Evolution API

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs. **Liste os ACs explicitamente** (sem intervalos): o eval só reconhece `AC-N`.
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`).
> Testes em `apps/social/tests/`, nomeados `test_AC_N_*`; **inclua o token literal `AC-N` num docstring/comentário** de cada teste.
> A Evolution é **sempre mockada** no transporte; testes não gravam no `MEDIA_ROOT` real; relógio injetado nos testes de orçamento.
> O corpo exato do Status **não está confirmado**: os testes usam o contrato isolado em `EvolutionClient`; a task 10 o fixa na sua instância.

## Plano
| #  | Task                                                                                                                                                                  | Cobre AC                                              | Depende de | Gate (comando)                                                                            | Status   |
|----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------|------------|-------------------------------------------------------------------------------------------|----------|
| 1  | Config e plataforma: `EVOLUTION_API_URL`/`EVOLUTION_TIMEOUT_SECONDS`, `.env.example`, `conf.evolution_configured()` (HTTPS), `Platform.WHATSAPP_STATUS` + migração, validação do nome da instância | AC-4, AC-14                                           | —          | `… test apps.social.tests.test_evolution_config` + `makemigrations --check`               | done     |
| 2  | `EvolutionClient`: host fixo, header `apikey`, nome codificado na rota, `connection_state`, `send_status` (texto/imagem base64), `EvolutionApiError`, timeout por chamada, sem segredos em log | AC-8, AC-9, AC-12, AC-14                              | 1          | `… test apps.social.tests.test_evolution_client`                                          | done     |
| 3  | Contas de WhatsApp: cadastro (valida `open`, chave cifrada), recadastro, "Verificar", "Desconectar", lista sem chave, aviso de não configurada, isolamento por usuário | AC-1, AC-2, AC-3, AC-4, AC-5, AC-14, AC-16            | 2          | `… test apps.social.tests.test_evolution_accounts_views`                                  | done     |
| 4  | Formulário de publicação: grupo "Status do WhatsApp", contas em reconexão/não configurada desabilitadas, imagem opcional sem Facebook, validações e seleção inválida | AC-6, AC-7, AC-16                                     | 3          | `… test apps.social.tests.test_evolution_post_form`                                       | done     |
| 5  | Publicador do WhatsApp + despacho em `send_pending`: texto/imagem, mensagens amigáveis, `needs_reauth` (401/403/404/≠`open`/conta já em reauth), falhas reenviáveis, imagem ausente | AC-8, AC-9, AC-11, AC-12                              | 2, 3       | `… test apps.social.tests.test_evolution_publisher apps.social.tests.test_publishing`     | done     |
| 6  | Orçamento de tempo: timeout = `min(config, restante − 25 s)`; < 40 s não inicia o alvo `[P]`                                                                           | AC-13                                                 | 5          | `… test apps.social.tests.test_publish_budget`                                            | done     |
| 7  | Destinos mistos (Facebook + Threads + WhatsApp), histórico/detalhe ("Status do WhatsApp", "link indisponível"), notas de supersessão nas specs 0003/0004; suíte existente verde | AC-10, AC-15                                          | 4, 5, 6    | `… test apps` + `node scripts/eval-spec-fidelity.mjs .`                                   | done     |
| 8  | Segurança transversal: chave/base64/texto fora de logs, HTML, mensagens e exceções; host só do servidor; nome de instância hostil rejeitado; isolamento entre usuários  | AC-14, AC-16                                          | 3, 5, 7    | `… test apps.social.tests.test_evolution_security`                                        | done     |
| 9  | Documentação: ADR-0010, README (aviso Baileys, chave da instância), `TESTING.md`, `STATE.md`, `lessons.md`, `.env.example`                                             | AC-17                                                 | 1–8        | `… test apps.social.tests.test_evolution_docs` + `node scripts/validate-mermaid.mjs .` | pendente |
| 10 | **Contrato real + UAT:** fixar corpo/base64/JID/estado na sua instância (versão), ajustar o cliente, publicar texto e imagem num número de teste, forçar falha e Tentar novamente | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17 | 1–9 | `docker compose exec web python manage.py test` + `makemigrations --check` + auditoria (`audit-esteira`, `validate-mermaid`, `eval-spec-fidelity`) + roteiro manual | pendente |

> Ordem sugerida: 1 → 2 → 3 → (4, 5) → 6 → 7 → 8 → 9 → 10. As tasks 4 e 5 só dependem da 3; a 6 pode andar junto da 7.
> Uma task só vira `done` quando o **gate passa** — não por inspeção. Um commit por task.
> **A task 10 depende de você:** a publicação é real e o Hub não apaga Status; use um número/grupo de teste e coloque `EVOLUTION_API_URL` no `.env` (a chave da instância é digitada na tela do Hub, nunca no chat).

## Plano de teste
- **Unidade:** nome da instância (válidos e hostis: `/`, `..`, `?`, `#`, `%`, espaço, > 64); `evolution_configured()` (HTTPS × HTTP × vazio); cliente (host fixo, header, rota codificada, corpo texto/imagem, mapeamento de erros por status, timeout repassado).
- **Integração:** cadastro e verificação com banco real e Evolution mockada (cada linha da matriz de cadastro); publicador com banco real (cada linha da matriz de envio); `send_pending` com relógio controlado; formulário (cada linha da matriz do formulário).
- **Aceite:** um teste por AC (`test_AC_N_*`); cada linha das **três matrizes** vira um caso.
- **Segurança:** busca da chave, do base64 e do texto em logs/HTML/mensagens (`assertLogs`, conteúdo renderizado); servidor falso que registra o host e o caminho realmente chamados.
- **Regressão:** suíte das 0002–0005 verde (371 testes hoje); atualizar só o que a nova plataforma tocar (textos "Selecione ao menos uma Página…" se mudarem).
- **UAT (task 10):** contrato lido na sua instância; Status de texto e de imagem num número de teste; instância desconectada → "Reconexão necessária"; falha forçada + Tentar novamente; conferir no celular.

## Divergências (SPEC_DEVIATION)
> Se a implementação precisar fugir da spec, registre aqui antes de seguir (ver `CLAUDE.md`).
- Nenhuma até agora.

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [ ] ADR-0010 registrado (credenciais por instância, host fixo, Baileys)
- [x] Glossário / context-map atualizados
- [ ] Specs 0003/0004 com a nota de supersessão e 0006 reflete o que foi construído
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] Cobertura e análise estática conforme `docs/engineering/TESTING.md`
