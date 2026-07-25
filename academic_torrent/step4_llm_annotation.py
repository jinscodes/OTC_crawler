from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    import step0_config as cfg
except ModuleNotFoundError:  # Supports: python -m academic_torrent.step4_llm_annotation
    from academic_torrent import step0_config as cfg


ENV_FILE = Path(cfg.BASE_DIR).parent / ".env"


def load_environment() -> None:
    """Load repository-level environment variables from .env."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is not installed. Run: "
            "pip install -r academic_torrent/requirements.txt"
        ) from exc

    load_dotenv(ENV_FILE)


def configured_model(explicit_model: str | None = None) -> str:
    """Resolve the model from a CLI override or OPENAI_MODEL in .env."""
    model = (explicit_model or os.getenv("OPENAI_MODEL") or "").strip()
    if not model:
        raise RuntimeError(f"OPENAI_MODEL is missing from {ENV_FILE}")
    return model


def _resolve_prompt_path(prompt_file: str | os.PathLike[str]) -> Path:
    path = Path(prompt_file).expanduser()
    if not path.is_absolute():
        path = ENV_FILE.parent / path
    return path


def load_annotation_prompt(
    *,
    prompt: str | None = None,
    prompt_file: str | os.PathLike[str] | None = None,
) -> str:
    """Load a CLI prompt override or the configured versioned prompt file."""
    if prompt is not None:
        resolved_prompt = prompt.strip()
        if not resolved_prompt:
            raise RuntimeError("The annotation prompt cannot be empty")
        return resolved_prompt

    configured_file = prompt_file or os.getenv("STEP4_PROMPT_FILE")
    if not configured_file:
        raise RuntimeError(f"STEP4_PROMPT_FILE is missing from {ENV_FILE}")

    path = _resolve_prompt_path(configured_file)
    try:
        resolved_prompt = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Could not read annotation prompt file {path}: {exc}"
        ) from exc
    if not resolved_prompt:
        raise RuntimeError(f"Annotation prompt file is empty: {path}")
    return resolved_prompt


def create_client():
    """Create an OpenAI client using OPENAI_API_KEY from the repository .env."""
    load_environment()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(f"OPENAI_API_KEY is missing from {ENV_FILE}")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "openai is not installed. Run: "
            "pip install -r academic_torrent/requirements.txt"
        ) from exc

    # The SDK retries transient connection, rate-limit, and server errors.
    return OpenAI(
        api_key=api_key,
        max_retries=cfg.STEP4_CLIENT_MAX_RETRIES,
        timeout=cfg.STEP4_CLIENT_TIMEOUT_SECONDS,
    )


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _record_key(post: dict, index: int) -> str:
    """Return a stable key for resume/checkpoint matching."""
    return str(post.get("post_id") or post.get("url") or f"index:{index}")


def _post_input(post: dict) -> str:
    """Serialize only fields useful to the annotator as a JSON user message."""
    payload = {
        "post_id": post.get("post_id"),
        "clean_text": post.get("clean_text"),
    }
    return json.dumps(payload, ensure_ascii=False)


def _usage_dict(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    out: dict[str, int] = {}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, field, None)
        if isinstance(value, int):
            out[field] = value
    return out


def annotate_post(
    client: Any,
    post: dict,
    *,
    model: str,
    prompt: str,
    max_output_tokens: int,
) -> dict:
    """Annotate one post and return a copy containing LLM result metadata."""
    response = client.responses.create(
        model=model,
        instructions=prompt,
        input=_post_input(post),
        max_output_tokens=max_output_tokens,
        store=False,
    )
    output_text = (getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise RuntimeError("The API returned no output text.")

    record = dict(post)
    record["llm_annotation"] = {
        "status": "completed",
        "text": output_text,
        "requested_model": model,
        "model": getattr(response, "model", model),
        "response_id": getattr(response, "id", None),
        "prompt_sha256": _prompt_hash(prompt),
        "annotated_at": cfg.now_iso(),
        "usage": _usage_dict(response),
    }
    return record


def _error_record(post: dict, model: str, prompt: str, exc: Exception) -> dict:
    record = dict(post)
    record["llm_annotation"] = {
        "status": "error",
        "error": f"{type(exc).__name__}: {exc}",
        "requested_model": model,
        "prompt_sha256": _prompt_hash(prompt),
        "attempted_at": cfg.now_iso(),
    }
    return record


def _is_reusable(record: dict, model: str, prompt_sha256: str) -> bool:
    annotation = record.get("llm_annotation") or {}
    return (
        annotation.get("status") == "completed"
        and annotation.get("requested_model") == model
        and annotation.get("prompt_sha256") == prompt_sha256
    )


def _write_json_atomic(path: str, data: Any) -> None:
    """Write JSON without risking a half-written checkpoint."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=parent, prefix=f".{os.path.basename(path)}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def _read_checkpoint(path: str) -> dict[str, dict]:
    """Read the recoverable per-request JSONL checkpoint, if one exists."""
    records: dict[str, dict] = {}
    if not os.path.exists(path):
        return records

    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            try:
                item = json.loads(line)
                records[str(item["key"])] = item["record"]
            except (json.JSONDecodeError, KeyError, TypeError):
                # A killed process can leave only the final JSONL line partial.
                print(
                    f"[step4] Warning: ignoring invalid checkpoint line "
                    f"{line_number} in {path}"
                )
    return records


def _append_checkpoint(path: str, key: str, record: dict) -> None:
    """Persist one finished API attempt without rewriting the large output."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as file:
        json.dump({"key": key, "record": record}, file, ensure_ascii=False)
        file.write("\n")


def annotate_one(
    subreddit: str,
    *,
    model: str,
    prompt: str,
    client: Any | None = None,
    max_output_tokens: int = cfg.STEP4_MAX_OUTPUT_TOKENS,
    progress_every: int = cfg.STEP4_PROGRESS_EVERY,
    max_consecutive_errors: int = cfg.STEP4_MAX_CONSECUTIVE_ERRORS,
    limit: int | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict:
    """Annotate one subreddit's Step 3 candidates and return run statistics."""
    input_path = cfg.step_path(cfg.DIR_STEP3, subreddit)
    candidates = cfg.read_json(input_path, default=None)
    if candidates is None:
        raise FileNotFoundError(f"{cfg.DIR_STEP3}/{subreddit}.json not found")
    if not isinstance(candidates, list):
        raise ValueError(f"{input_path} must contain a JSON list")

    output_path = cfg.step_path(cfg.DIR_STEP4, subreddit)
    checkpoint_path = f"{output_path}.checkpoint.jsonl"
    if dry_run:
        planned = min(len(candidates), limit) if limit is not None else len(candidates)
        print(
            f"[step4] r/{subreddit}: dry run — {planned:,} API calls planned "
            f"({len(candidates):,} candidates, model={model})"
        )
        return {
            "input": len(candidates),
            "planned": planned,
            "model": model,
            "dry_run": True,
        }

    if client is None:
        client = create_client()

    prompt_sha256 = _prompt_hash(prompt)
    existing = [] if overwrite else cfg.read_json(output_path, default=[]) or []
    if not isinstance(existing, list):
        raise ValueError(f"{output_path} must contain a JSON list")

    existing_by_key = {
        _record_key(record, index): record for index, record in enumerate(existing)
    }
    if overwrite:
        try:
            os.unlink(checkpoint_path)
        except FileNotFoundError:
            pass
    else:
        existing_by_key.update(_read_checkpoint(checkpoint_path))

    results_by_key: dict[str, dict] = {}
    reused = attempted = failed = consecutive_errors = 0

    # Preserve only completed annotations made with this exact prompt and model.
    for index, post in enumerate(candidates):
        key = _record_key(post, index)
        prior = existing_by_key.get(key)
        if prior is not None and _is_reusable(prior, model, prompt_sha256):
            results_by_key[key] = prior
            reused += 1

    try:
        for index, post in enumerate(candidates):
            key = _record_key(post, index)
            if key in results_by_key:
                continue
            if limit is not None and attempted >= limit:
                break

            attempted += 1
            try:
                results_by_key[key] = annotate_post(
                    client,
                    post,
                    model=model,
                    prompt=prompt,
                    max_output_tokens=max_output_tokens,
                )
                status = "completed"
                consecutive_errors = 0
            except Exception as exc:  # Keep the batch moving; resume retries errors.
                results_by_key[key] = _error_record(post, model, prompt, exc)
                failed += 1
                consecutive_errors += 1
                status = "error"

            _append_checkpoint(checkpoint_path, key, results_by_key[key])

            if attempted == 1 or attempted % progress_every == 0:
                print(
                    f"[step4] r/{subreddit}: attempted {attempted:,}, "
                    f"reused {reused:,}, latest={status}"
                )
            if consecutive_errors >= max_consecutive_errors:
                print(
                    f"[step4] r/{subreddit}: stopping after "
                    f"{consecutive_errors} consecutive API errors"
                )
                break
    except KeyboardInterrupt:
        print(f"\n[step4] r/{subreddit}: interrupted; saving checkpoint ...")
        raise
    finally:
        ordered = [
            results_by_key[_record_key(candidate, i)]
            for i, candidate in enumerate(candidates)
            if _record_key(candidate, i) in results_by_key
        ]
        _write_json_atomic(output_path, ordered)
        try:
            os.unlink(checkpoint_path)
        except FileNotFoundError:
            pass

    completed = sum(
        (record.get("llm_annotation") or {}).get("status") == "completed"
        for record in ordered
    )
    errors = len(ordered) - completed
    stats = {
        "input": len(candidates),
        "completed": completed,
        "errors": errors,
        "remaining": len(candidates) - completed,
        "attempted_this_run": attempted,
        "failed_this_run": failed,
        "reused": reused,
        "model": model,
        "prompt_sha256": prompt_sha256,
        "output": output_path,
    }
    cfg.update_summary(subreddit, "step4_llm_annotation", stats)
    print(
        f"[step4] r/{subreddit}: {completed:,} completed, {errors:,} errors, "
        f"{stats['remaining']:,} remaining"
    )
    return stats


def run(
    subreddits: list[str] | None = None,
    **annotation_options: Any,
) -> dict[str, dict]:
    """Run Step 4 for each configured or explicitly selected subreddit."""
    selected = subreddits or cfg.load_subreddits()
    dry_run = bool(annotation_options.get("dry_run"))
    prompt_file = annotation_options.pop("prompt_file", None)

    load_environment()
    model = configured_model(annotation_options.get("model"))
    prompt = load_annotation_prompt(
        prompt=annotation_options.get("prompt"),
        prompt_file=prompt_file,
    )
    annotation_options["model"] = model
    annotation_options["prompt"] = prompt

    client = None if dry_run else create_client()
    print(
        f"[step4] LLM annotation — subreddits: {selected}, model={model}, "
        f"prompt_sha256={_prompt_hash(prompt)[:12]}"
    )

    all_stats: dict[str, dict] = {}
    for subreddit in selected:
        try:
            all_stats[subreddit] = annotate_one(
                subreddit, client=client, **annotation_options
            )
        except FileNotFoundError as exc:
            print(f"[SKIP] r/{subreddit}: {exc}")
        except KeyboardInterrupt:
            print("[step4] Stopped by user.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] r/{subreddit}: {exc}")
    return all_stats


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "subreddits",
        nargs="*",
        help="Subreddits to annotate (default: all configured subreddits)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model (default: OPENAI_MODEL from .env)",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Direct annotation prompt override",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Prompt file override (default: STEP4_PROMPT_FILE from .env)",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=_positive_int,
        default=cfg.STEP4_MAX_OUTPUT_TOKENS,
    )
    parser.add_argument(
        "--progress-every",
        type=_positive_int,
        default=cfg.STEP4_PROGRESS_EVERY,
        help="Print a progress update after this many new API calls",
    )
    parser.add_argument(
        "--max-consecutive-errors",
        type=_positive_int,
        default=cfg.STEP4_MAX_CONSECUTIVE_ERRORS,
        help="Stop a subreddit after this many API errors in a row",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help="Maximum new API calls per subreddit (useful for testing)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignore existing Step 4 annotations and start again",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and count calls without calling the API",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        run(
            args.subreddits or None,
            model=args.model,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            max_output_tokens=args.max_output_tokens,
            progress_every=args.progress_every,
            max_consecutive_errors=args.max_consecutive_errors,
            limit=args.limit,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        raise SystemExit(f"[step4] ERROR: {exc}") from exc


if __name__ == "__main__":
    main()
