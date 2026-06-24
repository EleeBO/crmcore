#!/usr/bin/env python3
"""Health check script — verifies all CRM Copilot components.

Usage:
    python scripts/health_check.py [--backend-url http://localhost:8000]

Checks:
    1. Redis   — connect + PING
    2. ChromaDB — heartbeat
    3. SaluteSpeech — OAuth token acquisition
    4. Backend HTTP — GET /api/v1/health
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"

OK = f"{GREEN}✓ OK{RESET}"
FAIL = f"{RED}✗ FAIL{RESET}"
SKIP = f"{YELLOW}~ SKIP{RESET}"


def _load_env() -> dict[str, str]:
    """Read backend/.env without importing pydantic."""
    env_path = Path(__file__).parent.parent / "backend" / ".env"
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


# ── Checks ────────────────────────────────────────────────────────────────


async def check_redis(url: str) -> tuple[bool, str]:
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=3)
        await r.ping()
        await r.aclose()
        return True, f"PONG from {url}"
    except Exception as exc:
        return False, str(exc)


async def check_chromadb(path: str) -> tuple[bool, str]:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=path)
        client.heartbeat()
        return True, f"heartbeat OK at {path}"
    except Exception as exc:
        return False, str(exc)


async def check_salutespeech(api_key: str, scope: str) -> tuple[bool, str]:
    if not api_key:
        return False, "SBER_SPEECH_API_KEY not set"
    try:
        import httpx

        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={
                    "Authorization": f"Basic {api_key}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"scope": scope},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token", "")
            expires_at = data.get("expires_at", 0)
            remaining_s = int(expires_at / 1000 - time.time())
            return True, f"token obtained, expires in {remaining_s}s, scope={scope}"
    except Exception as exc:
        return False, str(exc)


async def check_backend_health(url: str) -> tuple[bool, str]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/api/v1/health")
            if resp.status_code == 404:
                return False, f"endpoint not found (is backend running at {url}?)"
            data = resp.json()
            status = data.get("status", "unknown")
            ok = resp.status_code in (200, 207)
            return ok, (
                f"HTTP {resp.status_code} — {status} "
                f"(redis={data.get('redis')}, chromadb={data.get('chromadb')})"
            )
    except httpx.ConnectError:
        return False, f"backend not reachable at {url} (not started?)"
    except Exception as exc:
        return False, str(exc)


# ── Main ──────────────────────────────────────────────────────────────────


async def run(backend_url: str = "http://localhost:8000") -> int:
    env = _load_env()

    redis_url = env.get("REDIS_URL", "redis://localhost:6379")
    chroma_dir = env.get("CHROMA_PERSIST_DIR", "./chroma_data")
    sber_key = env.get("SBER_SPEECH_API_KEY", os.getenv("SBER_SPEECH_API_KEY", ""))
    sber_scope = env.get("SBER_SPEECH_SCOPE", "SALUTE_SPEECH_PERS")

    print(f"\n{BOLD}=== CRM Copilot — Health Check ==={RESET}\n")

    checks = [
        ("Redis", check_redis(redis_url)),
        ("ChromaDB", check_chromadb(chroma_dir)),
        ("SaluteSpeech OAuth", check_salutespeech(sber_key, sber_scope)),
        ("Backend /health", check_backend_health(backend_url)),
    ]

    results = await asyncio.gather(*[c for _, c in checks], return_exceptions=True)

    failures = 0
    for (name, _), result in zip(checks, results):
        if isinstance(result, Exception):
            ok, msg = False, str(result)
        else:
            ok, msg = result  # type: ignore[misc]
        icon = OK if ok else FAIL
        print(f"  {icon}  {BOLD}{name}{RESET}: {msg}")
        if not ok:
            failures += 1

    print(f"\n{'All checks passed.' if failures == 0 else f'{failures} check(s) failed.'}\n")
    return failures


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Health check for CRM Copilot")
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(backend_url=args.backend_url)))


if __name__ == "__main__":
    main()
