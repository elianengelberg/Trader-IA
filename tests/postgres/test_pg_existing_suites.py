"""The persistence tests of the SQLite suite, run unchanged on PostgreSQL.

``persistence/database.py`` says PostgreSQL "is exercised by the same tests when a
server is reachable". This file is what makes that true: each test below is the original
function from ``tests/integration``, called as is, with its module's database factory
(``_db``) or settings factory (``_settings``) redirected to a PostgreSQL database of its
own (``tests.postgres.support.Redirect``). Nothing is copied, so a change to one of these
tests is a change to both runs.

Covered: the account journal and its restart (positions, partial fills, fees, the UTC
day, baselines, orphaned orders), funding settlements across a restart, the adverse
venue, the risk-state rebuild, the cross-process session lease, session-start atomicity
and the run lifecycle.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.integration import (
    test_account_restore as account_restore_suite,
)
from tests.integration import (
    test_account_restore_scope as account_restore_scope_suite,
)
from tests.integration import (
    test_adverse_recovery as adverse_recovery_suite,
)
from tests.integration import (
    test_funding_restore as funding_restore_suite,
)
from tests.integration import (
    test_live_api as live_api_suite,
)
from tests.integration import (
    test_risk_state_persistence as risk_state_persistence_suite,
)
from tests.integration import (
    test_run_lifecycle as run_lifecycle_suite,
)
from tests.integration import (
    test_session_lease as session_lease_suite,
)
from tests.integration import (
    test_session_start_atomicity as session_start_atomicity_suite,
)
from tests.postgres.support import Redirect

ACCOUNT_RESTORE = [
    "test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart",
    "test_a_drawdown_past_the_breaker_survives_a_restart",
    "test_restarting_before_and_after_midnight_utc_keeps_the_peak_and_rolls_the_day_correctly",
    "test_an_open_position_is_restored_protected_scorable_and_closable_after_a_restart",
    "test_a_resting_entry_left_by_a_dead_session_is_orphaned_not_resurrected",
    "test_a_pending_exit_at_restart_leaves_the_position_open_and_the_new_session_closes_it",
    "test_partial_fills_and_fees_rebuild_identically_however_often",
    "test_a_lost_journal_write_makes_the_rebuild_incomplete_and_the_next_session_blocked",
    "test_a_database_outage_during_a_write_does_not_pretend_the_state_was_saved",
    "test_fill_rows_without_journal_events_are_an_inconsistent_account",
    "test_legacy_fills_before_an_operator_baseline_are_set_aside_pinned_and_still_in_view",
    "test_a_baseline_seeds_a_runtime_flat_at_base_capital_and_lifts_the_block",
    "test_a_baseline_pins_the_legacy_set_so_it_cannot_grow_or_shrink_silently",
    "test_a_baseline_refuses_to_open_a_journal_that_already_has_a_record",
    "test_a_baseline_needs_legacy_fills_a_stopped_session_and_a_time_after_every_fill",
    "test_a_session_resumed_after_the_deploy_leaves_marks_that_do_not_block_the_baseline",
    "test_a_leg_entered_in_two_partial_fills_is_protected_and_closes_flat",
    "test_the_residue_the_12h_session_left_is_one_whole_lot_and_closes_flat",
    "test_the_12h_session_s_short_residue_with_its_funding_starts_and_closes",
]
ACCOUNT_SCOPE = [
    "test_a_live_runs_fills_do_not_move_the_paper_account",
    "test_the_application_rebuilds_the_paper_account_from_paper_live_runs_only",
]
FUNDING_RESTORE = [
    "test_a_restart_past_a_settlement_settles_it_from_its_own_data_and_never_the_one_already_paid",
    "test_a_restart_inside_the_period_already_paid_charges_nothing_again",
    "test_a_plan_without_a_pointer_joins_the_current_period_late",
    "test_a_redelivered_settlement_is_one_row_and_one_charge_in_the_rebuild",
]
ADVERSE_RECOVERY = [
    "test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole",
    "test_a_store_that_loses_the_fills_table_makes_the_rebuild_incomplete_and_the_next_session_blocked_but_managing",
]
RISK_STATE = [
    "test_a_restart_rebuilds_todays_entries_from_the_store_and_the_cap_still_binds",
    "test_a_replayed_fill_and_a_replayed_order_do_not_double_count",
    "test_the_rebuild_sees_yesterday_as_zero_entries_but_keeps_the_cooldown_anchor",
    "test_sessions_of_other_accounts_do_not_count",
]
SESSION_LEASE = [
    "test_a_start_is_refused_while_another_process_heartbeats_the_account",
    "test_a_start_proceeds_once_the_other_heartbeat_is_stale",
    "test_a_boot_does_not_resume_or_stamp_a_run_whose_heartbeat_keeps_advancing",
    "test_a_boot_resumes_a_run_whose_fresh_heartbeat_does_not_advance_after_the_probe",
    "test_a_boot_resumes_a_run_without_a_heartbeat_at_once",
    "test_a_running_session_stamps_its_heartbeat_and_a_clean_shutdown_releases_it",
    "test_the_sessions_own_run_is_not_a_foreign_lease",
]
START_ATOMICITY = [
    "test_two_simultaneous_start_requests_yield_one_session_and_one_run_row",
    "test_without_the_lock_two_concurrent_starts_build_two_runtimes",
    "test_a_second_sequential_start_is_refused_while_one_is_active",
    "test_a_failed_run_row_write_starts_nothing",
    "test_a_runtime_that_fails_to_start_leaves_a_stamped_row_and_no_session",
    "test_the_run_row_exists_before_the_loop_starts_so_a_first_cycle_fill_is_kept",
]
RUN_LIFECYCLE = [
    "test_a_run_whose_row_cannot_be_written_is_not_installed",
    "test_a_start_that_fails_stamps_its_row_and_installs_nothing",
    "test_two_concurrent_starts_yield_exactly_one_run",
    "test_stop_is_idempotent_and_stamps_the_row_once",
    "test_a_write_the_store_refuses_is_counted_and_degrades_health",
    "test_a_stop_that_arrives_during_a_start_waits_and_then_stops_the_session",
]


async def _run_original(module: ModuleType, name: str, *, redirect: Redirect, **available: Any) -> None:
    """Call ``module.name`` with the fixtures its signature asks for, by name, then
    check it really ran on PostgreSQL."""
    test = getattr(module, name, None)
    assert callable(test), f"{module.__name__}.{name} no longer exists: update this list"
    wanted = inspect.signature(test).parameters
    missing = [param for param in wanted if param not in available]
    assert not missing, f"{name} needs {missing}"
    await test(**{param: available[param] for param in wanted})
    redirect.assert_ran_on_postgresql(available["tmp_path"])


@pytest.mark.parametrize("name", ACCOUNT_RESTORE)
async def test_account_restore(name: str, redirect: Redirect, tmp_path: Path) -> None:
    redirect.database_factory(account_restore_suite)
    await _run_original(account_restore_suite, name, redirect=redirect, tmp_path=tmp_path)


@pytest.mark.parametrize("direction", ["short", "long"])
async def test_account_restore_restored_open_leg(direction: str, redirect: Redirect, tmp_path: Path) -> None:
    redirect.database_factory(account_restore_suite)
    name = "test_a_restored_open_leg_starts_at_its_base_capital_and_the_books_agree"
    await _run_original(account_restore_suite, name, redirect=redirect, tmp_path=tmp_path, direction=direction)


@pytest.mark.parametrize("name", ACCOUNT_SCOPE)
async def test_account_restore_scope(
    name: str, redirect: Redirect, tmp_path: Path, fake_public_feed: None
) -> None:
    redirect.database_factory(account_restore_scope_suite)
    # The second test imports ``_settings`` from test_live_api inside its body.
    redirect.settings_factory(live_api_suite)
    await _run_original(account_restore_scope_suite, name, redirect=redirect, tmp_path=tmp_path)


@pytest.mark.parametrize("name", FUNDING_RESTORE)
async def test_funding_restore(name: str, redirect: Redirect, tmp_path: Path) -> None:
    redirect.database_factory(funding_restore_suite)
    await _run_original(funding_restore_suite, name, redirect=redirect, tmp_path=tmp_path)


@pytest.mark.parametrize("name", ADVERSE_RECOVERY)
async def test_adverse_recovery(name: str, redirect: Redirect, tmp_path: Path) -> None:
    redirect.database_factory(adverse_recovery_suite)
    await _run_original(adverse_recovery_suite, name, redirect=redirect, tmp_path=tmp_path)


@pytest.mark.parametrize("name", RISK_STATE)
async def test_risk_state_persistence(name: str, redirect: Redirect, tmp_path: Path) -> None:
    redirect.database_factory(risk_state_persistence_suite)
    await _run_original(risk_state_persistence_suite, name, redirect=redirect, tmp_path=tmp_path)


@pytest.mark.parametrize("name", SESSION_LEASE)
async def test_session_lease(name: str, redirect: Redirect, tmp_path: Path, fake_public_feed: None) -> None:
    redirect.settings_factory(session_lease_suite)
    await _run_original(session_lease_suite, name, redirect=redirect, tmp_path=tmp_path)


@pytest.mark.parametrize("name", START_ATOMICITY)
async def test_session_start_atomicity(
    name: str, redirect: Redirect, tmp_path: Path, fake_public_feed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    redirect.settings_factory(session_start_atomicity_suite)
    await _run_original(session_start_atomicity_suite, name, redirect=redirect, tmp_path=tmp_path, monkeypatch=monkeypatch)


@pytest.mark.parametrize("name", RUN_LIFECYCLE)
async def test_run_lifecycle(
    name: str, redirect: Redirect, tmp_path: Path, fake_public_feed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    redirect.settings_factory(run_lifecycle_suite)
    await _run_original(run_lifecycle_suite, name, redirect=redirect, tmp_path=tmp_path, monkeypatch=monkeypatch)
