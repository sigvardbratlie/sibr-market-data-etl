#!/usr/bin/env python3
"""Valgfri hjelper: genererer deploy/helm/sibr-market/values.secrets.yaml (gitignored)
fra modulenes lokale .env-filer, så du slipper å lime inn base64-nøkler for hånd.

    python3 deploy/scripts/env-to-values.py
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deploy/helm/sibr-market/values.secrets.yaml"
SKIP = {"GOOGLE_APPLICATION_CREDENTIALS"}  # filsti på Mac; i clusteret brukes *_JSON

def parse(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = re.sub(r"^export\s+", "", k).strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k not in SKIP:
            out[k] = v
    return out

lines = ["# GENERERT av deploy/scripts/env-to-values.py – gitignored, ikke commit.", "secrets:"]
for m in ["scraping", "modeling", "api", "cadastral"]:
    env = ROOT / m / ".env"
    if not env.exists():
        print(f"⚠️  hopper over {m} (mangler .env)")
        continue
    data = parse(env)
    lines.append(f"  sibr-{m}-env:")
    lines += [f"    {k}: {json.dumps(v)}" for k, v in data.items()]  # JSON-strenger er gyldig YAML
    print(f"✔ sibr-{m}-env: {', '.join(data)}")
OUT.write_text("\n".join(lines) + "\n")
OUT.chmod(0o600)
print(f"Skrev {OUT.relative_to(ROOT)} (kun lokalt).")
print("Secretene opprettes i clusteret først når du kjører: make deploy")
