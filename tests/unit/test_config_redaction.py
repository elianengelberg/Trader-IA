"""No secret leaves ``Settings.redacted()`` (Phase 1.4): a webhook URL is a credential."""

from __future__ import annotations

from pydantic import SecretStr

from tia.core.config import Environment, LiveConfig, ObservabilityConfig, settings_for_env

TOKEN = "AbCdEf0123456789_secret-token-value"  # noqa: S105 - a marker to search for, not a credential


def _settings():  # type: ignore[no-untyped-def]
    base = settings_for_env(Environment.TESTING)
    return base.model_copy(
        update={
            "observability": ObservabilityConfig(
                alert_webhook_url=f"https://discord.com/api/webhooks/1234567890/{TOKEN}"
            ),
            "live": LiveConfig(
                binance_api_key=SecretStr("key-" + TOKEN), binance_api_secret=SecretStr("sec-" + TOKEN)
            ),
            "anthropic_api_key": SecretStr("sk-ant-" + TOKEN),
            "database_url": f"postgresql+asyncpg://tia:{TOKEN}@postgres:5432/tia",
        }
    )


def test_the_webhook_token_is_withheld_and_the_host_kept() -> None:
    redacted = _settings().redacted()
    url = redacted["observability"]["alert_webhook_url"]
    assert TOKEN not in url
    assert url == "https://discord.com/***"


def test_no_secret_appears_anywhere_in_the_redacted_document() -> None:
    import json

    dumped = json.dumps(_settings().redacted())
    assert TOKEN not in dumped
    assert "sk-ant-" not in dumped and "key-" not in dumped and "sec-" not in dumped


def test_an_empty_webhook_stays_empty() -> None:
    base = settings_for_env(Environment.TESTING)
    assert base.redacted()["observability"]["alert_webhook_url"] == ""
