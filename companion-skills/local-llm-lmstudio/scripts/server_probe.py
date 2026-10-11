#!/usr/bin/env python3
"""Probe a local LLM server (LM Studio / llama.cpp / Ollama-compatible).

GETs /v1/models BYPASSING the system proxy (the #1 cause of WinError 10054 on
machines with VPN/antivirus web-shields) and prints the model ids — the exact
strings to pass as "model" in chat/completions requests. On the typical
failures it prints the cure from the local-llm-lmstudio skill.

stdlib only. Usage:
  python scripts/server_probe.py                      # http://127.0.0.1:1234
  python scripts/server_probe.py --host http://127.0.0.1:8080
"""
import argparse
import json
import socket
import sys
import urllib.error
import urllib.request

print(">> server_probe.py v1 loaded", flush=True)


def main():
    ap = argparse.ArgumentParser(
        description="Health-check a local OpenAI-compatible LLM server "
                    "(GET /v1/models, system proxy bypassed).")
    ap.add_argument("--host", default="http://127.0.0.1:1234",
                    help="server base URL (default: %(default)s; prefer "
                         "127.0.0.1 over localhost)")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="seconds to wait (default: %(default)s)")
    args = ap.parse_args()

    url = args.host.rstrip("/") + "/v1/models"
    # Empty ProxyHandler = ignore system/env proxies; they intercept localhost.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=args.timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"!! HTTP {e.code} from {url}: {e.reason}")
        print("   Server is up but unhappy; check the LM Studio Developer tab log.")
        sys.exit(1)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        reason = getattr(e, "reason", e)
        msg = str(reason)
        print(f"!! cannot reach {url}: {msg}")
        if "10054" in msg or "reset" in msg.lower():
            print("   WinError 10054 / connection reset: a VPN, corporate proxy or")
            print("   antivirus web-shield intercepts localhost. This probe already")
            print("   bypasses the system proxy — do the same in your client code:")
            print("     opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))")
            print("   Use 127.0.0.1 (not localhost) and add the app to AV exclusions.")
        elif "refused" in msg.lower() or "10061" in msg:
            print("   Connection refused: the server is not listening on this port.")
            print("   LM Studio: Developer tab -> Start Server (default port 1234);")
            print("   check the port in --host matches the one shown there.")
        elif "timed out" in msg.lower():
            print("   Timeout: server busy loading a model, or wrong host/port.")
        sys.exit(1)

    models = data.get("data", [])
    if not models:
        print("Server is up, but NO models are listed.")
        print("Load a model in LM Studio (or rely on JIT load by exact model id).")
        sys.exit(2)

    print(f"Server OK at {url} — {len(models)} model(s):")
    for m in models:
        print(f"  {m.get('id')}")
    print('Use these ids verbatim as "model" in /v1/chat/completions.')


if __name__ == "__main__":
    main()
