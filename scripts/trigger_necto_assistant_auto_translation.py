
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


URLS = {
    "live": "https://nectoassistant.mikroe.com/api/v1/necto-assistant-config/runtime-language/auto-translate",
    "dev": "https://nectoassistant.mikroe.dev/api/v1/necto-assistant-config/runtime-language/auto-translate",
}


def load_targets(path: str) -> dict[str, list[str]]:
    target_path = Path(path)

    if not target_path.exists():
        return {}

    data = json.loads(target_path.read_text(encoding="utf-8", errors="replace"))

    if not isinstance(data, dict):
        raise ValueError(f"Invalid targets file: {target_path}")

    result = {}

    for env, locales in data.items():
        if env not in URLS or not isinstance(locales, list):
            continue

        clean_locales = []

        for locale in locales:
            locale = str(locale).strip()
            if locale and locale not in clean_locales:
                clean_locales.append(locale)

        if clean_locales:
            result[env] = clean_locales

    return result


def response_text(response: requests.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False)
    except Exception:
        return response.text


def trigger_locale(
    *,
    env: str,
    locale: str,
    token: str | None,
    interval_seconds: int,
    request_timeout_seconds: int,
    max_wait_minutes: int,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "NECTO-general-packages-indexing",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = URLS[env]
    started_at = time.monotonic()
    attempt = 0

    while True:
        attempt += 1
        elapsed_seconds = int(time.monotonic() - started_at)

        if max_wait_minutes > 0 and elapsed_seconds > max_wait_minutes * 60:
            raise TimeoutError(
                f"Timed out waiting for NECTO Assistant {env.upper()} "
                f"auto-translation for {locale} after {max_wait_minutes} minutes."
            )

        print("")
        print(f"[NECTO ASSISTANT] {env.upper()} {locale} attempt {attempt}")

        try:
            response = requests.post(
                url,
                headers=headers,
                json={"locales": [locale]},
                timeout=request_timeout_seconds,
            )
        except requests.exceptions.ReadTimeout:
            print(
                f"[NECTO ASSISTANT] Request timeout for {env}/{locale}. "
                f"Waiting {interval_seconds}s before retry."
            )
            time.sleep(interval_seconds)
            continue
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Failed to call {env} auto-translation API: {exc}") from exc

        if response.status_code == 409:
            print(
                f"[NECTO ASSISTANT] Another auto-translation job is running on {env}. "
                f"Waiting {interval_seconds}s before retrying {locale}."
            )
            time.sleep(interval_seconds)
            continue

        if response.status_code != 200:
            raise RuntimeError(
                f"NECTO Assistant {env} auto-translation failed for {locale}: "
                f"HTTP {response.status_code}: {response_text(response)}"
            )

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(
                f"NECTO Assistant {env} auto-translation returned ok=false for {locale}: "
                + json.dumps(data, ensure_ascii=False)
            )

        print(f"[NECTO ASSISTANT] {env.upper()} auto-translation completed for {locale}")
        return data

def dispatch_private_import_workflow(
    *,
    token: str,
    repo: str,
    workflow_file: str,
    ref: str,
    environment: str,
    locale: str,
    target_branch: str,
) -> None:
    if not token:
        raise RuntimeError("Missing NECTO_ASSISTANT_IMPORT_PR_TOKEN.")

    if not repo or "/" not in repo:
        raise RuntimeError(
            "Missing or invalid NECTO_ASSISTANT_IMPORT_PR_REPO. "
            "Expected format: owner/repo."
        )

    if not workflow_file:
        raise RuntimeError("Missing NECTO_ASSISTANT_IMPORT_PR_WORKFLOW.")

    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"

    payload = {
        "ref": ref,
        "inputs": {
            "environment": environment,
            "locale": locale,
            "target_branch": target_branch,
        },
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "NECTO-general-packages-indexing",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code != 204:
        raise RuntimeError(
            f"Failed to dispatch private import workflow for {environment}/{locale}. "
            f"HTTP {response.status_code}: {response.text}"
        )

    print(
        f"[GITHUB] Dispatched {workflow_file} in {repo} "
        f"for {environment}/{locale}"
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets-file", default="tmp/necto_assistant_auto_translation_targets.json")
    parser.add_argument("--token", default=None)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--request-timeout-seconds", type=int, default=30)
    parser.add_argument("--max-wait-minutes", type=int, default=240)
    parser.add_argument(
        "--dispatch-import-pr",
        action="store_true",
        help="Dispatch private NECTO Assistant repo workflow after each successful locale import.",
    )

    args = parser.parse_args()

    targets = load_targets(args.targets_file)

    if not targets:
        print("[NECTO ASSISTANT] No auto-translation targets. Skipping.")
        return

    for env in ["dev", "live"]:
        for locale in targets.get(env, []):
            trigger_locale(
                env=env,
                locale=locale,
                token=args.token,
                interval_seconds=max(5, args.interval_seconds),
                request_timeout_seconds=max(5, args.request_timeout_seconds),
                max_wait_minutes=args.max_wait_minutes,
            )

            if args.dispatch_import_pr:
                dispatch_private_import_workflow(
                    token=os.environ.get("NECTO_ASSISTANT_IMPORT_PR_TOKEN", "").strip(),
                    repo=os.environ.get("NECTO_ASSISTANT_IMPORT_PR_REPO", "").strip(),
                    workflow_file=os.environ.get(
                        "NECTO_ASSISTANT_IMPORT_PR_WORKFLOW",
                        "import-runtime-language.yaml",
                    ).strip(),
                    ref=os.environ.get("NECTO_ASSISTANT_IMPORT_PR_REF", "main").strip(),
                    environment=env,
                    locale=locale,
                    target_branch=os.environ.get(
                        "NECTO_ASSISTANT_IMPORT_PR_TARGET_BRANCH",
                        "main",
                    ).strip(),
                )

    print("")
    print("[NECTO ASSISTANT] All requested auto-translations completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)