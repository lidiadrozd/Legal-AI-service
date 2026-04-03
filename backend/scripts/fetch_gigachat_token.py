"""One-off: получить access_token GigaChat и сохранить в gigachat_token.tmp"""
import base64
import json
import sys
import uuid
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# backend/ as cwd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

def main() -> int:
    cid = (settings.GIGACHAT_CLIENT_ID or "").strip()
    sec = (settings.GIGACHAT_CLIENT_SECRET or "").strip()
    scope = (settings.GIGACHAT_SCOPE or "GIGACHAT_API_PERS").strip()

    if not cid or not sec:
        print("ERROR: В .env задайте GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET", file=sys.stderr)
        return 1

    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = requests.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {basic}",
        },
        data=f"scope={scope}",
        timeout=30,
        verify=False,
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}

    if not r.ok:
        print("HTTP", r.status_code, json.dumps(body, ensure_ascii=False)[:800], file=sys.stderr)
        return 1

    token = body.get("access_token")
    if not token:
        print("ERROR: Нет access_token:", json.dumps(body, ensure_ascii=False)[:500], file=sys.stderr)
        return 1

    backend_root = Path(__file__).resolve().parents[1]
    out_path = backend_root / "gigachat_token.tmp"
    payload = {
        "access_token": token,
        "expires_at": body.get("expires_at"),
        "expires_in": body.get("expires_in"),
        "scope_used": scope,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    header_path = backend_root / "gigachat_auth_header.tmp"
    header_path.write_text(f"Authorization: Bearer {token}\n", encoding="utf-8")
    print(f"OK: {out_path}")
    print(f"OK: {header_path} (скопируйте строку в Postman / curl)")
    print("scope:", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
