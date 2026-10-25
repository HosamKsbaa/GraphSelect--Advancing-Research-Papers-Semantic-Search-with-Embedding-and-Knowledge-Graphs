"""Nano-USD (`10^-9` USD) spending ledger with pre-call reservation and hard caps.

Ported and generalized from `alrs_tool/benchmarks/experiment_budget.py` (commit 865cd08).
Reserves worst-case cost *before* any external call and optionally persists to a locked JSON file.
"""

from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from engines.errors import ProviderError

NANO_USD_PER_DOLLAR = 1_000_000_000
DEFAULT_LIMIT_NANO_USD = 5_000_000_000  # $5.00 hard cap

BudgetProvider = Literal["gemini_embedding", "gemini_flash", "jev", "openalex"]

DEFAULT_RESERVATION_NANO_USD: dict[BudgetProvider, int] = {
    "gemini_embedding": 8192 * 200,  # 1,638,400 nano-USD ($0.0016384)
    "gemini_flash": 4096 * 150 + 1024 * 600,  # 1,228,800 nano-USD ($0.0012288)
    "jev": 65536 * 42,  # 2,752,512 nano-USD ($0.002752512)
    "openalex": 1_000,  # nominal polite-pool tracking unit
}


class BudgetExceededError(ProviderError):
    """Raised before an external call when the reservation would exceed the hard cap."""

    def __init__(self, message: str) -> None:
        super().__init__("budget_exceeded", message, retryable=False)


class BudgetCallReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    provider: BudgetProvider
    reserved_nano_usd: int = Field(gt=0)
    spent_nano_usd: int = Field(ge=0)
    status: Literal["reserved", "completed", "failed"] = "reserved"
    reserved_at: str
    failure_reason: str | None = None


class BudgetLedgerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit_nano_usd: int = Field(gt=0)
    committed_nano_usd: int = Field(ge=0)
    remaining_nano_usd: int = Field(ge=0)
    calls: list[BudgetCallReceipt] = Field(default_factory=list)


class SpendingLedger:
    """Pre-call nano-USD reservation ledger with optional file-locked persistence."""

    def __init__(
        self,
        limit_nano_usd: int = DEFAULT_LIMIT_NANO_USD,
        ledger_path: Path | None = None,
    ) -> None:
        if limit_nano_usd <= 0:
            raise ValueError("limit_nano_usd must be positive.")
        self.limit_nano_usd = limit_nano_usd
        self.ledger_path = ledger_path.resolve() if ledger_path is not None else None
        self._receipts: dict[str, BudgetCallReceipt] = {}
        if self.ledger_path is not None and self.ledger_path.exists():
            self._load_from_disk()

    @property
    def committed_nano_usd(self) -> int:
        total = 0
        for receipt in self._receipts.values():
            if receipt.status == "reserved":
                total += receipt.reserved_nano_usd
            elif receipt.status == "completed":
                total += receipt.spent_nano_usd
            elif receipt.status == "failed":
                total += receipt.spent_nano_usd
        return total

    @property
    def remaining_nano_usd(self) -> int:
        return max(0, self.limit_nano_usd - self.committed_nano_usd)

    @property
    def committed_usd(self) -> float:
        return self.committed_nano_usd / NANO_USD_PER_DOLLAR

    @property
    def limit_usd(self) -> float:
        return self.limit_nano_usd / NANO_USD_PER_DOLLAR

    def snapshot(self) -> BudgetLedgerSnapshot:
        return BudgetLedgerSnapshot(
            limit_nano_usd=self.limit_nano_usd,
            committed_nano_usd=self.committed_nano_usd,
            remaining_nano_usd=self.remaining_nano_usd,
            calls=list(self._receipts.values()),
        )

    def reserve(
        self,
        provider: BudgetProvider,
        amount_nano_usd: int | None = None,
    ) -> BudgetCallReceipt:
        reserved = (
            amount_nano_usd
            if amount_nano_usd is not None
            else DEFAULT_RESERVATION_NANO_USD[provider]
        )
        if reserved <= 0:
            raise ValueError("Reservation amount must be positive.")
        if self.committed_nano_usd + reserved > self.limit_nano_usd:
            raise BudgetExceededError(
                f"Budget cap exceeded: reserving {reserved} nano-USD for {provider} "
                f"would exceed limit {self.limit_nano_usd} nano-USD."
            )
        receipt = BudgetCallReceipt(
            receipt_id=str(uuid4()),
            provider=provider,
            reserved_nano_usd=reserved,
            spent_nano_usd=reserved,
            status="reserved",
            reserved_at=datetime.now(timezone.utc).isoformat(),
        )
        self._receipts[receipt.receipt_id] = receipt
        self._persist_to_disk()
        return receipt

    def complete(
        self,
        receipt_id: str,
        actual_nano_usd: int | None = None,
    ) -> BudgetCallReceipt:
        receipt = self._receipts.get(receipt_id)
        if receipt is None:
            raise KeyError(f"Unknown budget receipt: {receipt_id}")
        spent = (
            actual_nano_usd
            if actual_nano_usd is not None
            else receipt.reserved_nano_usd
        )
        if spent < 0 or spent > receipt.reserved_nano_usd:
            raise ValueError(
                "Actual spend must be non-negative and within the reserved allowance."
            )
        updated = receipt.model_copy(
            update={"spent_nano_usd": spent, "status": "completed"}
        )
        self._receipts[receipt_id] = updated
        self._persist_to_disk()
        return updated

    def fail(
        self,
        receipt_id: str,
        reason: str = "provider_call_failed",
        retain_reservation: bool = False,
    ) -> BudgetCallReceipt:
        receipt = self._receipts.get(receipt_id)
        if receipt is None:
            raise KeyError(f"Unknown budget receipt: {receipt_id}")
        spent = receipt.reserved_nano_usd if retain_reservation else 0
        updated = receipt.model_copy(
            update={
                "spent_nano_usd": spent,
                "status": "failed",
                "failure_reason": reason,
            }
        )
        self._receipts[receipt_id] = updated
        self._persist_to_disk()
        return updated

    def _load_from_disk(self) -> None:
        assert self.ledger_path is not None
        raw = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        snap = BudgetLedgerSnapshot.model_validate(raw)
        self.limit_nano_usd = snap.limit_nano_usd
        self._receipts = {r.receipt_id: r for r in snap.calls}

    def _persist_to_disk(self) -> None:
        if self.ledger_path is None:
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.ledger_path.with_suffix(self.ledger_path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                payload = self.snapshot().model_dump_json(indent=2)
                self.ledger_path.write_text(payload, encoding="utf-8")
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


__all__ = [
    "BudgetCallReceipt",
    "BudgetExceededError",
    "BudgetLedgerSnapshot",
    "BudgetProvider",
    "DEFAULT_LIMIT_NANO_USD",
    "DEFAULT_RESERVATION_NANO_USD",
    "NANO_USD_PER_DOLLAR",
    "SpendingLedger",
]
