---
name: tasks
description: Decomposição e gates da feature 0017 (central de conexões em /contas/). Puxe ao implementar.
alwaysApply: false
---

# Tasks — Central de conexões

> Testes em `apps/social/tests/test_connections_hub.py` (um `test_AC_N_*` por critério; seguidores em
> `test_connections_followers.py` com os clientes HTTP simulados, como nos testes existentes).
> Gate geral: `.venv/bin/python manage.py test apps` + `npm run build`.

## Plano
| # | Task | Cobre AC | Depende de | Gate (comando) | Status |
|---|------|----------|------------|----------------|--------|
| 0 | **Spike (doc oficial)**: campo de seguidores da Página do Facebook, do IG User e do Threads (endpoint + permissão). Registrar a resposta na spec ("Pontos a confirmar"). Threads exige `threads_manage_insights` → decidido: "—" | AC-9 | — | revisão | done |
| 1 | Modelo: `SocialAccount.followers_count` (`PositiveIntegerField`, nulo) + migração | AC-6, AC-9 | 0 | `manage.py makemigrations --check` | done |
| 2 | Clientes: leitura de seguidores em `GraphClient` (Página e IG User; o Threads fica de fora, ver task 0), com testes de contrato (params, parse, erro) | AC-9 | 0 | `manage.py test apps.social.tests.test_connections_followers` | done |
| 3 | `AccountCheckView`: após verificar, ler seguidores e gravar `followers_count`; falha sem erro de token mantém o valor e o status; WhatsApp e Threads ficam nulos; redirect para `/contas/?rede=<rede>` (também no `account_disconnect`) | AC-9, AC-11 | 1, 2 | idem | done |
| 4 | `AccountsView`: montar o contexto por rede (ordem fixa, contas do perfil, estado do ícone pela matriz, contagem de alvos `published` por conta numa só query, integração configurada, URL de conectar/reconectar) e a seleção inicial com `?rede=` | AC-2, AC-4, AC-6, AC-8, AC-10 | 1 | `manage.py test apps.social.tests.test_connections_hub` | done |
| 5 | Template `social/accounts.html` reescrito: `tablist` de ícones (links `?rede=`), painel conectado (cabeçalho, pares rótulo/valor, sincronização, chips de permissões, ações), lista de contas (2+), painel desconectado, botão primário pela matriz; sem tokens no HTML | AC-1, AC-2, AC-6, AC-7, AC-8, AC-10, AC-11, AC-13 | 4 | idem | done |
| 6 | Estilos (Tailwind, tokens existentes): coluna/painel, botão quadrado, indicadores, destaque laranja, hover, tooltip, breakpoint 768 px (ícones em linha acima do painel), fade ≤ 200 ms com `prefers-reduced-motion`; `npm run build:css` | AC-1, AC-2, AC-3, AC-12, AC-14 | 5 | `npm run build` + UAT | done |
| 7 | JS da troca sem recarregar (ilha em `frontend/mui/` ou módulo leve): troca de painel e de conta, `aria-selected`, setas/Enter/Espaço, `history.replaceState`, fallback de avatar quebrado | AC-5, AC-7, AC-13 | 5 | `npm run build` + UAT no navegador | done |
| 8 | UAT no navegador: desktop e celular, tema escuro e claro, rede conectada/desconectada/reconexão, 2 Páginas, sem JS | AC-1–AC-14 | 6, 7 | UAT | done |
| 9 | Docs vivas: glossário (Rede, Central de conexões), README se mudar algo de config, STATE | — | 1–8 | revisão | done |

## Plano de teste
- Unidade/contrato: parse do número de seguidores por cliente; erro de token × erro transitório (task 2).
- Integração (views): seleção inicial e `?rede=` inválido (AC-4); estado do ícone por linha da matriz (AC-2);
  painel conectado com os campos e "—"/"Nunca" (AC-6); 2+ contas (AC-7); painel desconectado e
  integração não configurada por rede (AC-8); atualizar com sucesso/falha transitória/erro de token
  e WhatsApp (AC-9); reconectar e desconectar com redirect `?rede=` e 404 para conta alheia (AC-10, AC-11);
  atributos ARIA no HTML (AC-13); nenhum token no HTML.
- Aceite visual (UAT, task 8): AC-1, AC-3, AC-5, AC-12, AC-14 — comportamento no navegador, não testável só pelo HTML.

## Divergências (SPEC_DEVIATION)
- [x] Task 5 · AC-8 pedia "Integração não configurada"; os testes das specs 0004/0006 exigem a mensagem por rede · resolução: **spec atualizada** (mensagem por rede)

## Checklist de Definition of Done
- [x] Todos os AC verdes **pelo gate executável** (985 testes; AC-1/3/5/12/14 também no UAT)
- [x] Nenhum `SPEC_DEVIATION` pendente (AC-8 ajustado na spec, não no código)
- [x] ADR não necessário: o Threads ficou sem seguidores (task 0)
- [x] Glossário atualizado (Central de conexões, Rede, Seguidores)
- [x] Spec reflete o que foi construído
- [x] `docs/STATE.md` atualizado (próximo passo / decisões)
