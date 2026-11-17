---
name: context-map
description: Bounded contexts e relações. Puxe ao modelar ou cruzar contextos.
alwaysApply: false
---

# Context Map

> Visão DDD estratégica: os bounded contexts do sistema e como se relacionam.
> Atualize quando uma feature cria/move fronteiras. Combine com diagramas C4 se útil.

## Bounded Contexts
| Contexto   | Subdomínio (core/supporting/generic) | Responsabilidade        | Dono |
|------------|--------------------------------------|-------------------------|------|
| Social (integrações) | core | Conectar e operar contas de redes sociais (Meta); guarda tokens com segurança | Thalyson |
| Identidade (`accounts`) | generic | Autenticação e dados do usuário (Django auth) | Thalyson |
| Painel (`dashboard`) | supporting | Visão geral e indicadores | Thalyson |

## Relações entre contextos
> Padrões de integração DDD: Customer/Supplier, Conformist, Anti-Corruption Layer (ACL),
> Shared Kernel, Open Host Service, Published Language.

```
[Meta Graph API] ──(ACL: GraphClient)──► [Social (integrações)]
                                              │
                      (Conformist: User FK)   ├──► [Identidade]
                                              │
                    (Customer/Supplier)       └──► [Painel]
```

| Upstream   | Downstream | Padrão              | Por quê |
|------------|------------|---------------------|---------|
| Meta Graph API | Social | Anti-Corruption Layer | `GraphClient` protege o modelo do Hub dos formatos e versões da Meta |
| Identidade | Social | Conformist | Social só referencia o `User` do Django por FK |
| Social | Painel | Customer/Supplier | O Painel consulta as contas conectadas (somente leitura) |

## Diagramas
Os diagramas de arquitetura de alto nível (contexto C4, containers, mapa de contextos) ficam em
[`diagrams.md`](./diagrams.md) — gere/atualize com a skill `/diagramar`.
