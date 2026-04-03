#!/usr/bin/env python3
# Purpose: Download a Hugging Face Hub repository into a local folder via the `hf`/`huggingface-cli` CLI.
# Dependencies: huggingface_hub package (provides `huggingface-cli` or `hf`), Python 3.8+.
# Usage:
#   export HF_TOKEN=<your_access_token>
#   python3 hf_down.py /path/to/folder [--repo-name NAME] [--namespace RogersPyke] [--repo-type model|dataset]
#       [--batch-size N] [--max-retries -1] [--retry-base-seconds 5] [--retry-max-seconds 300]
#
#   python3 hf_down.py /path/to/folder --token <your_access_token>
#
# Note: --commit-message is accepted for CLI parity with hf_up.py but ignored (downloads do not create commits).

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, TypeVar

LOG_DIR = Path(__file__).resolve().parent / "logs"
DEFAULT_NAMESPACE = "RogersPyke"
ENV_TOKEN = "HF_TOKEN"


def _utc8_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def _setup_logging() -> logging.Logger:
    """
    @input: None
    @output: logging.Logger configured for file + stderr
    @scenario: Consistent log layout for download operations
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc8_now().strftime("%Y%m%d%H%M%S")
    log_path = LOG_DIR / f"hf_download_{ts}.log"
    logger = logging.getLogger("hf_download")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("[%(name)s] [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.debug("Log file: %s", log_path)
    return logger


def resolve_token(cli_token: Optional[str], logger: logging.Logger) -> Optional[str]:
    """
    @input: cli_token Optional[str]; logger
    @output: str token or None if missing
    @scenario: Token from --token or HF_TOKEN
    """
    t = (cli_token or os.environ.get(ENV_TOKEN) or "").strip()
    if not t:
        logger.error("Missing token: pass --token or set %s", ENV_TOKEN)
        return None
    return t


def sanitize_repo_name(name: str) -> str:
    """
    @input: str raw folder/repo name
    @output: str safe repo segment for Hugging Face repo_id
    @scenario: Map folder basename to valid repo name
    """
    s = name.strip().strip("/")
    if not s:
        return "download-repo"
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return s or "download-repo"


def find_hf_cli(logger: logging.Logger) -> Optional[str]:
    """
    @input: logger
    @output: str path to hf or huggingface-cli executable, or None if missing
    @scenario: Ensure CLI is available before subprocess calls
    """
    for cmd in ("hf", "huggingface-cli"):
        p = shutil.which(cmd)
        if p:
            return p
    logger.error(
        "'hf' or 'huggingface-cli' not found. Install: pip install huggingface_hub"
    )
    return None


def _argv_for_log(argv: List[str]) -> str:
    """Redact token values in argv for safe logging."""
    out: List[str] = []
    skip_next = False
    for a in argv:
        if skip_next:
            out.append("<redacted>")
            skip_next = False
            continue
        if a in ("--token", "-t") or (a.startswith("--token=") or a.startswith("-t=")):
            if "=" in a:
                out.append(a.split("=", 1)[0] + "=<redacted>")
            else:
                out.append(a)
                skip_next = True
        else:
            out.append(a)
    return " ".join(out)


_T = TypeVar("_T")


def _chunks(items: List[_T], size: int) -> Iterable[List[_T]]:
    """Yield consecutive slices of `items` with length at most `size` (size must be >= 1)."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def run_cmd(
    logger: logging.Logger,
    argv: List[str],
    cwd: Optional[str] = None,
) -> None:
    """
    @input: logger; argv full command list; cwd optional working directory
    @output: None; raises CalledProcessError on failure
    @scenario: Run hf/huggingface-cli with inherited stdio so TTY-aware CLIs show live progress on console
    """
    logger.info("RUN: %s", _argv_for_log(argv))
    logger.debug(
        "Subprocess inherits stdout/stderr (no capture); CLI output appears on console only.",
    )
    r = subprocess.run(argv, cwd=cwd)
    if r.returncode != 0:
        logger.error(
            "Command failed (exit %s): %s",
            r.returncode,
            " ".join(argv),
        )
        r.check_returncode()


def run_cmd_with_retry(
    logger: logging.Logger,
    argv: List[str],
    cwd: Optional[str] = None,
    *,
    max_retries: int = -1,
    retry_base_seconds: float = 5.0,
    retry_max_seconds: float = 300.0,
) -> None:
    """
    @input: logger; argv; cwd; max_retries (-1=unlimited, 0=fail on first error);
            retry_base_seconds; retry_max_seconds cap for backoff
    @output: None on success
    @scenario: Retry subprocess until success or finite limit
    """
    failures = 0
    while True:
        try:
            run_cmd(logger, argv, cwd)
            return
        except subprocess.CalledProcessError:
            if max_retries >= 0 and failures >= max_retries:
                logger.error("Giving up after %s failed attempt(s)", failures + 1)
                raise
            delay = min(
                retry_base_seconds * (2**failures),
                retry_max_seconds,
            )
            logger.warning(
                "Command failed (attempt %s); retrying in %.1fs",
                failures + 1,
                delay,
            )
            time.sleep(delay)
            failures += 1


def _top_level_remote_paths(
    repo_id: str,
    repo_type: str,
    token: str,
    logger: logging.Logger,
) -> List[str]:
    """
    @input: repo_id, repo_type, token, logger
    @output: sorted list of unique top-level path names in the remote repo
    @scenario: Batched download mirrors batched upload by hub entry name
    """
    try:
        from huggingface_hub import HfApi
    except ImportError:
        logger.error(
            "huggingface_hub Python package required for --batch-size > 0 "
            "(listing remote files). Install: pip install huggingface_hub"
        )
        raise
    api = HfApi()
    try:
        files = api.list_repo_files(
            repo_id=repo_id,
            repo_type=repo_type,
            token=token,
        )
    except Exception as e:
        logger.exception("Failed to list repo files: %s", e)
        raise
    roots: set[str] = set()
    for f in files:
        f = (f or "").strip()
        if not f:
            continue
        roots.add(f.split("/")[0])
    return sorted(roots)


def ensure_repo_download(
    *,
    cli: str,
    token: str,
    repo_id: str,
    folder: Path,
    repo_type: str,
    logger: logging.Logger,
    commit_message: Optional[str],
    batch_size: int,
    max_retries: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> None:
    """
    @input: hf/huggingface-cli path, token, repo_id namespace/name, local destination folder,
            repo_type model|dataset; batch_size (<=0: one full-repo download; >0: top-level
            remote entries per batch pass); retry settings for all CLI calls
    @output: None on success
    @scenario: download repo into folder, batched or one shot (no repo create; repo must exist)
    """
    if commit_message:
        logger.debug("--commit-message is ignored for download (parity with hf_up.py CLI only)")

    folder.mkdir(parents=True, exist_ok=True)

    if batch_size <= 0:
        download_argv = [
            cli,
            "download",
            repo_id,
            "--local-dir",
            str(folder.resolve()),
            "--token",
            token,
            "--repo-type",
            repo_type,
        ]
        run_cmd_with_retry(
            logger,
            download_argv,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )
        logger.info("Done: downloaded %s -> %s (single download)", repo_id, folder)
        return

    entries = _top_level_remote_paths(repo_id, repo_type, token, logger)
    if not entries:
        logger.warning("No files in remote repo %s; nothing to download", repo_id)
        return

    total_batches = (len(entries) + batch_size - 1) // batch_size
    for batch_idx, batch in enumerate(_chunks(entries, batch_size), start=1):
        logger.info(
            "Download batch %s/%s (%s item(s))",
            batch_idx,
            total_batches,
            len(batch),
        )
        for entry in batch:
            download_argv = [
                cli,
                "download",
                repo_id,
                entry,
                "--local-dir",
                str(folder.resolve()),
                "--token",
                token,
                "--repo-type",
                repo_type,
            ]
            run_cmd_with_retry(
                logger,
                download_argv,
                max_retries=max_retries,
                retry_base_seconds=retry_base_seconds,
                retry_max_seconds=retry_max_seconds,
            )
    logger.info("Done: downloaded %s -> %s (batched)", repo_id, folder)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    @input: argv optional list (for tests)
    @output: argparse.Namespace
    @scenario: CLI for folder path and optional overrides
    """
    p = argparse.ArgumentParser(
        description="Download a Hugging Face Hub repo into a local folder using hf/huggingface-cli.",
    )
    p.add_argument(
        "folder",
        type=str,
        help="Local directory to download into (repo name defaults to folder basename).",
    )
    p.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Hugging Face namespace/user (default: {DEFAULT_NAMESPACE}).",
    )
    p.add_argument(
        "--repo-name",
        default=None,
        help="Remote repo name; default: sanitized basename of folder.",
    )
    p.add_argument(
        "--token",
        default=None,
        help=f"Hugging Face access token; else read from env {ENV_TOKEN}.",
    )
    p.add_argument(
        "--repo-type",
        choices=("model", "dataset"),
        default="dataset",
        help="Repository type (default: dataset).",
    )
    p.add_argument(
        "--commit-message",
        default=None,
        help="Ignored for download; accepted for CLI parity with hf_up.py.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Top-level remote paths per batch pass (default: 20). Each path is one CLI download. "
        "Use 0 for a single download of the whole repo.",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=-1,
        help="Max retries per CLI after failure (-1=until success, 0=fail fast).",
    )
    p.add_argument(
        "--retry-base-seconds",
        type=float,
        default=5.0,
        help="Initial backoff for retries (default: 5).",
    )
    p.add_argument(
        "--retry-max-seconds",
        type=float,
        default=300.0,
        help="Max backoff between retries (default: 300).",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """
    @input: argv optional CLI tokens
    @output: int exit code 0 ok, non-zero on error
    @scenario: End-to-end Hub download into a local folder
    """
    logger = _setup_logging()
    args = parse_args(argv)
    folder = Path(args.folder).expanduser().resolve()
    if folder.exists() and not folder.is_dir():
        logger.error("Not a directory: %s", folder)
        return 1
    token = resolve_token(args.token, logger)
    if not token:
        return 2
    cli = find_hf_cli(logger)
    if not cli:
        return 127
    base = args.repo_name or folder.name
    repo_name = sanitize_repo_name(base)
    ns = sanitize_repo_name(args.namespace)
    repo_id = f"{ns}/{repo_name}"
    logger.info("repo_id=%s folder=%s repo_type=%s", repo_id, folder, args.repo_type)
    try:
        ensure_repo_download(
            cli=cli,
            token=token,
            repo_id=repo_id,
            folder=folder,
            repo_type=args.repo_type,
            logger=logger,
            commit_message=args.commit_message,
            batch_size=args.batch_size,
            max_retries=args.max_retries,
            retry_base_seconds=args.retry_base_seconds,
            retry_max_seconds=args.retry_max_seconds,
        )
    except subprocess.CalledProcessError:
        return 1
    except Exception:
        logger.exception("Download failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
