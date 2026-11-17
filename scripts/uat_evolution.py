#!/usr/bin/env python3
"""UAT do contrato da Evolution API (spec 0006, task 10) — roda NO SEU TERMINAL, sem Django.

O que faz (a chave é digitada aqui, nunca vai para chat, arquivo nem log, e é ocultada na saída):
  1. versão da Evolution (sem chave);
  2. estado da conexão da instância;
  3. quantos contatos a instância conhece (só contagem) — `allContacts=true` usa os contatos que a Evolution tem com nome;
  4. (opcional, pede confirmação a cada passo) envia um Status de teste SOMENTE para o SEU número, em 3 variações:
     texto, imagem em base64 puro e imagem em base64 com prefixo `data:` — para descobrir qual formato a sua versão aceita.

Nada é enviado aos seus contatos: o Status de teste usa `allContacts=false` e `statusJidList=[seu número]`.
Mesmo assim ele é um Status real do seu número (visível a você em "Meu status"; expira em ~24 h).

Uso:
    python3 scripts/uat_evolution.py --url https://sua-evolution.exemplo.com --instance minha-instancia
"""
import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 60


def call(method, url, key=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if key:
        headers["apikey"] = key
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # rede, DNS, timeout
        return None, type(exc).__name__.encode()


def parse(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def redact(text, key):
    return text.replace(key, "<chave>") if key else text


def brief(payload, raw, key, limit=300):
    """Resumo curto e seguro da resposta: só campos de erro/estado, chave ocultada, tamanho limitado."""
    if isinstance(payload, dict):
        picked = {k: payload[k] for k in ("status", "error", "message", "response", "state") if k in payload}
        text = json.dumps(picked or {"keys": sorted(payload)[:8]}, ensure_ascii=False)
    else:
        text = raw.decode("utf-8", "replace")
    return redact(text, key)[:limit]


def ask(question):
    return input(f"{question} [s/N] ").strip().lower() in ("s", "sim", "y", "yes")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("EVOLUTION_API_URL", ""), help="origem HTTPS da Evolution")
    parser.add_argument("--instance", default="", help="nome da instância")
    parser.add_argument("--image", default=str(ROOT / "exemplos" / "teste-publicacao.jpg"), help="imagem de teste (JPEG)")
    args = parser.parse_args()

    base = args.url.strip().rstrip("/")
    if not base.startswith("https://"):
        sys.exit("Informe --url com a origem HTTPS da Evolution (ou EVOLUTION_API_URL).")
    instance = args.instance.strip() or input("Nome da instância: ").strip()
    key = getpass.getpass("Chave da INSTÂNCIA (não aparece ao digitar): ").strip()
    if not instance or not key:
        sys.exit("Instância e chave são obrigatórias.")

    results = []

    def record(name, status, text):
        results.append((name, status, text))
        print(f"  → {name}: HTTP {status} {text}")

    print("\n1) Versão (sem chave)")
    status, raw = call("GET", f"{base}/")
    payload = parse(raw)
    version = payload.get("version") if isinstance(payload, dict) else None
    record("versão", status, f"version={version}")

    print("\n2) Estado da conexão")
    status, raw = call("GET", f"{base}/instance/connectionState/{instance}", key)
    payload = parse(raw)
    state = (payload or {}).get("instance", {}).get("state") if isinstance(payload, dict) else None
    record("connectionState", status, f"state={state!r}" if state else brief(payload, raw, key))

    print("\n3) Contatos conhecidos pela instância (só contagem; é o que `allContacts=true` usa)")
    status, raw = call("POST", f"{base}/chat/findContacts/{instance}", key, {"where": {}})
    payload = parse(raw)
    if isinstance(payload, list):
        named = sum(1 for c in payload if isinstance(c, dict) and c.get("pushName"))
        record("contatos", status, f"total={len(payload)} com_nome={named}")
        if named == 0:
            print("  ! Nenhum contato com nome: `allContacts=true` pode não alcançar ninguém.")
    else:
        record("contatos", status, brief(payload, raw, key))

    print("\n4) Status de teste SOMENTE para o seu número (allContacts=false)")
    if not ask("Enviar Status de teste agora?"):
        print("\nResumo (pode colar no chat; não contém a chave):")
        for name, status, text in results:
            print(f"- {name}: HTTP {status} {text}")
        return

    number = "".join(ch for ch in input("Seu número com DDI, só dígitos (ex.: 5511999999999): ") if ch.isdigit())
    if len(number) < 10:
        sys.exit("Número inválido.")
    jid = f"{number}@s.whatsapp.net"
    url = f"{base}/message/sendStatus/{instance}"
    audience = {"allContacts": False, "statusJidList": [jid]}

    variants = [("texto", {"type": "text", "content": "Teste UAT Social Hub (texto)", "backgroundColor": "#128C7E", "font": 1, **audience})]
    image_path = Path(args.image)
    if image_path.is_file():
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        variants.append(("imagem base64 puro", {"type": "image", "content": encoded, "caption": "Teste UAT Social Hub (imagem)", **audience}))
        variants.append(("imagem data-URI", {"type": "image", "content": f"data:image/jpeg;base64,{encoded}", "caption": "Teste UAT Social Hub (data URI)", **audience}))
    else:
        print(f"  ! Imagem de teste não encontrada ({image_path}); só o texto será testado.")

    for name, body in variants:
        if not ask(f"Enviar variação «{name}» para o seu número?"):
            continue
        status, raw = call("POST", url, key, body)
        payload = parse(raw)
        ok = isinstance(payload, dict) and isinstance(payload.get("key"), dict) and "id" in payload["key"]
        record(f"sendStatus {name}", status, "aceito (key.id presente)" if ok else brief(payload, raw, key))

    print("\nAgora confira no celular, em «Meu status», qual variação apareceu e como (texto/imagem/legenda).")
    print("\nResumo (pode colar no chat; não contém a chave nem seu número):")
    for name, status, text in results:
        print(f"- {name}: HTTP {status} {text}")


if __name__ == "__main__":
    main()
