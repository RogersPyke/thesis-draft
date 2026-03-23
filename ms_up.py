#!/usr/bin/env python3
# Purpose: Upload a local folder to ModelScope as a repository via the `modelscope` CLI.
# Dependencies: modelscope package (provides `modelscope` console script), Python 3.8+.
# Usage:
#   export MS_TOKEN=<your_sdk_token>
#   python3 upload.py /path/to/folder [--repo-name NAME] [--namespace rogerspyke] [--repo-type model|dataset]
#
#   python3 upload.py /path/to/folder --token <your_sdk_token>

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

LOG_DIR = Path(__file__).resolve().parent / "logs"
DEFAULT_NAMESPACE = "rogerspyke"
ENV_TOKEN = "MS_TOKEN"


def _utc8_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def _setup_logging() -> logging.Logger:
    """
    @input: None
    @output: logging.Logger configured for file + stderr
    @scenario: Consistent log layout for upload operations
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc8_now().strftime("%Y%m%d%H%M%S")
    log_path = LOG_DIR / f"upload_{ts}.log"
    logger = logging.getLogger("upload")
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
    @scenario: Token from --token or MS_TOKEN
    """
    t = (cli_token or os.environ.get(ENV_TOKEN) or "").strip()
    if not t:
        logger.error("Missing token: pass --token or set %s", ENV_TOKEN)
        return None
    return t


def sanitize_repo_name(name: str) -> str:
    """
    @input: str raw folder/repo name
    @output: str safe repo segment for ModelScope repo_id
    @scenario: Map folder basename to valid repo name
    """
    s = name.strip().strip("/")
    if not s:
        return "upload-repo"
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return s or "upload-repo"


def find_modelscope_cli(logger: logging.Logger) -> Optional[str]:
    """
    @input: logger
    @output: str path to modelscope executable, or None if missing
    @scenario: Ensure CLI is available before subprocess calls
    """
    p = shutil.which("modelscope")
    if not p:
        logger.error("'modelscope' CLI not found. Install: pip install modelscope")
        return None
    return p


def _argv_for_log(argv: List[str]) -> str:
    """Redact token values in argv for safe logging."""
    out: List[str] = []
    skip_next = False
    for a in argv:
        if skip_next:
            out.append("<redacted>")
            skip_next = False
            continue
        if a == "--token":
            out.append(a)
            skip_next = True
        else:
            out.append(a)
    return " ".join(out)


def run_cmd(
    logger: logging.Logger,
    argv: List[str],
    cwd: Optional[str] = None,
) -> None:
    """
    @input: logger; argv full command list; cwd optional working directory
    @output: None; raises CalledProcessError on failure
    @scenario: Run modelscope subcommands with captured output in logs
    """
    logger.info("RUN: %s", _argv_for_log(argv))
    r = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    if r.stdout:
        logger.debug("stdout:\n%s", r.stdout.rstrip())
    if r.stderr:
        logger.debug("stderr:\n%s", r.stderr.rstrip())
    if r.returncode != 0:
        logger.error(
            "Command failed (exit %s): %s",
            r.returncode,
            " ".join(argv),
        )
        if r.stdout:
            sys.stdout.write(r.stdout)
        if r.stderr:
            sys.stderr.write(r.stderr)
        r.check_returncode()


def ensure_repo_and_upload(
    *,
    cli: str,
    token: str,
    repo_id: str,
    folder: Path,
    repo_type: str,
    logger: logging.Logger,
    commit_message: Optional[str],
) -> None:
    """
    @input: modelscope path, token, repo_id namespace/name, local folder, repo_type model|dataset
    @output: None on success
    @scenario: create repo (exist_ok) then upload folder contents to repo root
    """
    create_argv = [
        cli,
        "create",
        repo_id,
        "--token",
        token,
        "--repo_type",
        repo_type,
    ]
    upload_argv = [
        cli,
        "upload",
        repo_id,
        str(folder.resolve()),
        "--token",
        token,
        "--repo-type",
        repo_type,
    ]
    if commit_message:
        upload_argv.extend(["--commit-message", commit_message])
    run_cmd(logger, create_argv)
    run_cmd(logger, upload_argv)
    logger.info("Done: uploaded %s -> %s", folder, repo_id)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    @input: argv optional list (for tests)
    @output: argparse.Namespace
    @scenario: CLI for folder path and optional overrides
    """
    p = argparse.ArgumentParser(
        description="Upload a folder to ModelScope using the modelscope CLI.",
    )
    p.add_argument(
        "folder",
        type=str,
        help="Local directory to upload (repo name defaults to folder basename).",
    )
    p.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"ModelScope namespace/user (default: {DEFAULT_NAMESPACE}).",
    )
    p.add_argument(
        "--repo-name",
        default=None,
        help="Remote repo name; default: sanitized basename of folder.",
    )
    p.add_argument(
        "--token",
        default=None,
        help=f"ModelScope SDK token; else read from env {ENV_TOKEN}.",
    )
    p.add_argument(
        "--repo-type",
        choices=("model", "dataset"),
        default="model",
        help="Repository type (default: model).",
    )
    p.add_argument(
        "--commit-message",
        default=None,
        help="Optional commit message for the upload commit.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """
    @input: argv optional CLI tokens
    @output: int exit code 0 ok, non-zero on error
    @scenario: End-to-end folder upload to ModelScope
    """
    logger = _setup_logging()
    args = parse_args(argv)
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        logger.error("Not a directory: %s", folder)
        return 1
    token = resolve_token(args.token, logger)
    if not token:
        return 2
    cli = find_modelscope_cli(logger)
    if not cli:
        return 127
    base = args.repo_name or folder.name
    repo_name = sanitize_repo_name(base)
    ns = sanitize_repo_name(args.namespace)
    repo_id = f"{ns}/{repo_name}"
    logger.info("repo_id=%s folder=%s repo_type=%s", repo_id, folder, args.repo_type)
    try:
        ensure_repo_and_upload(
            cli=cli,
            token=token,
            repo_id=repo_id,
            folder=folder,
            repo_type=args.repo_type,
            logger=logger,
            commit_message=args.commit_message,
        )
    except subprocess.CalledProcessError:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
