"""The holdout partition's procedural protection: an access ledger, not a vault.

Nothing in a repository can make a partition of a CSV unreadable. What can be done is to
make every computation of the holdout a recorded, named event: which dataset (by content
hash), under which configuration (criteria, strategies, horizons, split, seed, the
strategy code itself), how many variants had been tried on validation, what the verdicts
were, which commit, and whether the tree was clean. The ledger is append-only JSON lines;
a second computation of the same dataset refuses to run unless the operator names a
reason, and that reason is written down too.

Protocol (documented in docs/STRATEGY_IMPROVEMENT_PHASE.md §7, Phase 1.1 update):

1. Freeze strategy, parameters, methodology and acceptance criteria. Record them.
2. Compute the holdout **once**, with ``--unlock-holdout``. The ledger records it.
3. Any change motivated by the holdout result requires a *new* out-of-sample period:
   the holdout that informed the change is spent and cannot judge the change.

Limits, stated plainly: the ledger is a file an operator can delete; the dataset hash
does not prevent evaluating a re-cut of the same data; and none of this detects a
holdout computed by other means. It makes the honest path the easy path, nothing more.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path("data/runtime/holdout_access.jsonl")


@dataclass(frozen=True)
class HoldoutAccess:
    at: str
    dataset_id: str
    config_hash: str
    variants_on_validation: int
    verdicts: dict[str, str] = field(default_factory=dict)
    git_head: str = "unknown"
    git_dirty: bool | None = None
    reason: str = ""
    reopen: bool = False
    #: ``opened`` is written *before* the holdout is computed, ``completed`` after, with
    #: the verdicts. A process that dies in between leaves the opened line: the access
    #: happened and is counted (Phase 1.3). Lines from before this field read as completed.
    status: str = "completed"
    #: sha256/16 of the uncommitted changes in the tree at the time of the access (F11):
    #: a dirty tree is named by *what* was dirty, not only flagged as dirty.
    tree_digest: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def config_hash(config: dict[str, Any], *, code_paths: Iterable[Path] = ()) -> str:
    """blake2s/16 of the configuration *and* the strategy source files named.

    A holdout opened under one strategy implementation does not cover another: the code
    is part of what was frozen.
    """
    digest = hashlib.blake2s(digest_size=16)
    digest.update(json.dumps(config, sort_keys=True, default=str).encode("utf-8"))
    for path in sorted(Path(p) for p in code_paths):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def dirty_tree_digest(root: Path | None = None) -> str:
    """sha256/16 of ``git diff`` (the uncommitted changes), ``""`` when clean or when git
    is unavailable. What a ``dirty`` flag cannot say: *which* dirty tree computed this."""
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        diff = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [git, "diff"], capture_output=True, text=True, cwd=root, timeout=10, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    if not diff.strip():
        return ""
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()[:16]


def frozen_code_paths(src_root: Path) -> list[Path]:
    """Every source file whose change changes an experiment's result (F11): the
    strategies, the backtester, the execution simulator and its filters, the risk engine
    and budget, the features and regimes, and the instrument universe. Before this the
    frozen hash covered ``tia/strategy`` alone, and a changed fill rule or sizing rule
    could pass for the same experiment."""
    tia = src_root
    files: set[Path] = set()
    for folder in ("strategy", "backtest", "execution", "risk", "quant", "regime"):
        files.update((tia / folder).glob("*.py"))
    files.add(tia / "domain" / "instruments.py")
    files.add(tia / "economics" / "costs.py")
    files.add(tia / "economics" / "expected_value.py")
    return sorted(path for path in files if path.exists())


def git_state(root: Path | None = None) -> tuple[str, bool | None]:
    """``(head, dirty)``; ``("unknown", None)`` when git is unavailable."""
    git = shutil.which("git")
    if git is None:
        return ("unknown", None)
    try:
        head = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, cwd=root, timeout=10, check=False,
        ).stdout.strip()
        status = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [git, "status", "--porcelain"], capture_output=True, text=True, cwd=root, timeout=10, check=False,
        ).stdout
        return (head or "unknown", bool(status.strip()))
    except Exception:
        return ("unknown", None)


class HoldoutLedger:
    """Append-only record of holdout computations. One line per access."""

    def __init__(self, path: Path = DEFAULT_LEDGER) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def entries(self) -> list[HoldoutAccess]:
        if not self._path.exists():
            return []
        out: list[HoldoutAccess] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                out.append(HoldoutAccess(**{k: raw.get(k, v) for k, v in asdict(_EMPTY).items()}))
            except (ValueError, TypeError):
                continue  # a corrupt line is not a reason to lose the rest
        return out

    def prior(self, dataset_id: str) -> list[HoldoutAccess]:
        return [e for e in self.entries() if e.dataset_id == dataset_id]

    def check(self, *, dataset_id: str, config_hash: str, reopen_reason: str) -> tuple[bool, str]:
        """Whether computing the holdout for ``dataset_id`` is allowed now, and why.

        Allowed on first access. A prior access refuses unless ``reopen_reason`` names
        why; a prior access under the *same* configuration refuses even then — the same
        question asked twice of the same data has only one honest answer, the first.
        """
        prior = self.prior(dataset_id)
        if not prior:
            return (True, "first access to this dataset's holdout")
        same = [e for e in prior if e.config_hash == config_hash]
        if same:
            opened_only = all(e.status == "opened" for e in same)
            how = "opened (and never completed)" if opened_only else "already computed"
            return (
                False,
                f"the holdout of dataset {dataset_id} was {how} under this exact "
                f"configuration at {same[0].at}; a repeat adds no information and is refused"
                + (" — the opened access counts: the data was read" if opened_only else ""),
            )
        if not reopen_reason.strip():
            return (
                False,
                f"the holdout of dataset {dataset_id} was already computed ({len(prior)} time(s), "
                f"first at {prior[0].at}); reopening it under a changed configuration requires "
                "--holdout-reopen-reason, and the change must not have been motivated by the "
                "holdout result",
            )
        return (True, f"reopened under a changed configuration: {reopen_reason.strip()}")

    def record(self, access: HoldoutAccess) -> None:
        """Append one line under an exclusive file lock (F11): two runs that unlock the
        same holdout at the same moment cannot interleave their lines, and each sees the
        other's once it holds the lock. The lock is advisory and POSIX; where it is not
        available the append still happens, unlocked."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            locked = False
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                locked = True
            except (ImportError, OSError):
                locked = False
            try:
                handle.write(json.dumps(access.as_dict(), sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                if locked:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def open_access(self, *, dataset_id: str, config_hash: str, variants_on_validation: int,
                    git_head: str, git_dirty: bool | None, reason: str, at: str,
                    tree_digest: str = "") -> HoldoutAccess:
        """Write the ``opened`` line *before* any holdout number exists, so an access that
        dies mid-computation is still on record (Phase 1.3). Returns what was written; the
        caller records the ``completed`` line, with the verdicts, afterwards."""
        access = HoldoutAccess(
            at=at, dataset_id=dataset_id, config_hash=config_hash,
            variants_on_validation=variants_on_validation, git_head=git_head, git_dirty=git_dirty,
            reason=reason, reopen=bool(reason.strip()), status="opened", tree_digest=tree_digest,
        )
        self.record(access)
        return access


_EMPTY = HoldoutAccess(at="", dataset_id="", config_hash="", variants_on_validation=0)


__all__ = [
    "DEFAULT_LEDGER",
    "HoldoutAccess",
    "HoldoutLedger",
    "config_hash",
    "dirty_tree_digest",
    "frozen_code_paths",
    "git_state",
]
