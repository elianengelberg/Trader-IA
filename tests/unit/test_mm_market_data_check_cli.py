"""The market data check's venue flags: Mainnet public data by default (paper reads it),
Spot Testnet on request, never a mix, and the profile records the venue it was measured
against. No network: the guard refuses before anything connects."""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def check_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("mm_market_data_check")
    finally:
        sys.path.remove(str(SCRIPTS))


MAINNET_REST, MAINNET_STREAM = "https://api.binance.com", "wss://stream.binance.com:9443/stream"
TESTNET_REST, TESTNET_STREAM = "https://testnet.binance.vision", "wss://stream.testnet.binance.vision/stream"


def test_the_defaults_are_mainnet_public_data_so_paper_mode_is_unchanged(check_module) -> None:  # type: ignore[no-untyped-def]
    from tia.mm.streams import DEFAULT_STREAM_URL

    assert check_module.DEFAULT_REST_URL == MAINNET_REST and DEFAULT_STREAM_URL == MAINNET_STREAM
    assert check_module._same_venue(check_module.DEFAULT_REST_URL, DEFAULT_STREAM_URL)


def test_snapshots_and_stream_must_come_from_the_same_venue(check_module) -> None:  # type: ignore[no-untyped-def]
    assert check_module._same_venue(TESTNET_REST, TESTNET_STREAM)
    assert not check_module._same_venue(MAINNET_REST, TESTNET_STREAM)
    assert not check_module._same_venue(TESTNET_REST, MAINNET_STREAM)


def test_the_profile_source_names_the_hosts_it_was_measured_against(check_module) -> None:  # type: ignore[no-untyped-def]
    label = check_module._venue_label(TESTNET_REST, TESTNET_STREAM)
    assert label == "scripts/mm_market_data_check.py @ stream stream.testnet.binance.vision snapshots testnet.binance.vision"
    assert "testnet.binance.vision" not in check_module._venue_label(MAINNET_REST, MAINNET_STREAM)


def test_the_cli_refuses_a_venue_mix_before_connecting_anywhere(check_module, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sys, "argv", ["mm_market_data_check.py", "--rest-url", TESTNET_REST, "--stream-url", MAINNET_STREAM, "--no-record", "--minutes", "0.01"])
    assert asyncio.run(check_module.main()) == 2
    assert "REFUSED" in capsys.readouterr().out
