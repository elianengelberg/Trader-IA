| Id | Defecto simulado | T15 (36 archivos) | T21 (44 archivos) | Prueba que lo detecta en T21 |
|---|---|---|---|---|
| M01 | dos stops si la cancelación no se confirma | MUERTO | MUERTO | `test_partial_fills_and_fees_rebuild_identically_however_often` |
| M02 | segundo stop cuando el venue no sabe del primero | MUERTO | MUERTO | `test_a_venue_that_cannot_be_read_keeps_the_stop_tracked_and_places_not` |
| M03 | no esperar al stop de respuesta perdida | MUERTO | MUERTO | `test_no_second_stop_while_the_venue_cannot_say_whether_the_first_arriv` |
| M04 | ignorar el cambio de cantidad (stop más chico que la posición) | VIVO | MUERTO | `test_a_stop_is_resized_when_the_position_it_covers_changes_size[0.5]` |
| M05 | rechazo del stop en silencio (R25 original) | MUERTO | MUERTO | `test_a_venue_that_refuses_every_stop_blocks_entries_halts_and_keeps_as` |
| M06 | stop rechazado tomado como protección | MUERTO | MUERTO | `test_a_stop_rejected_as_an_order_is_handled_like_a_refused_one` |
| M07 | stop protector sin reduce_only | MUERTO | MUERTO | `test_a_venue_flat_behind_a_tracked_round_trip_blocks_entries_and_score` |
| M08 | stop del lado equivocado | MUERTO | MUERTO | `test_an_open_position_is_restored_protected_scorable_and_closable_afte` |
| M09 | redondeo del nivel hacia el lado que agranda la pérdida | VIVO | MUERTO | `test_the_stop_level_is_rounded_toward_the_position_on_the_venue_grid[T` |
| M10 | re-protección sin mirar si el estado admite órdenes reductoras | VIVO | MUERTO | `test_a_session_that_may_not_send_orders_does_not_reprotect_but_says_so` |
| M11 | sin re-protección tras un cierre que no trabaja (R18) | MUERTO | MUERTO | `test_every_bar_boundary_finds_the_position_protected_while_closes_are_` |
| M12 | sin re-protección tras un cierre no enviado (R18) | VIVO | MUERTO | `test_a_close_that_is_not_sent_puts_the_stop_back_in_the_same_call` |
| M13 | sin re-protección de la posición restaurada al arrancar (N5) | MUERTO | MUERTO | `test_a_position_restored_after_a_restart_is_protected_before_its_first` |
| M14 | más de un stop en reposo al reiniciar sin bloquear | VIVO | MUERTO | `test_two_stops_resting_against_a_restored_position_halt_the_session` |
| M15 | flush «completo» con escrituras fallidas (R19) | MUERTO | MUERTO | `test_a_lost_journal_write_makes_the_rebuild_incomplete_and_the_next_se` |
| M16 | cierre de emergencia a mercado encima de un stop que puede seguir en reposo | MUERTO | MUERTO | `test_a_flatten_whose_cancels_fail_keeps_the_stop_tracked_and_sends_no_` |
| M17 | cancelar todo olvida órdenes cuya cancelación no se confirmó | MUERTO | MUERTO | `test_a_flatten_whose_cancels_fail_keeps_the_stop_tracked_and_sends_no_` |
| M18 | estado desconocido sin detener las entradas | VIVO | MUERTO | `test_an_entry_the_venue_cannot_resolve_halts_entries_and_none_follows` |
| M19 | error de transporte después de enviar tomado como no enviado (N1) | MUERTO | MUERTO | `test_an_order_that_may_have_reached_the_venue_is_unknown_not_unsent[Re` |
| M20 | timeInForce enviado con STOP_LOSS | MUERTO | MUERTO | `test_a_stop_is_sent_as_stop_loss_with_a_stop_price_and_nothing_else` |
| M21 | la compuerta no exige el stop aceptado en testnet (R25) | MUERTO | MUERTO | `test_live_activation_needs_a_venue_that_accepted_the_protective_stop` |
| M22 | posición desprotegida sin detener órdenes nuevas | MUERTO | MUERTO | `test_a_venue_that_refuses_every_stop_blocks_entries_halts_and_keeps_as` |

**Muertos:** T15 16 de 22 · T21 22 de 22.

| Id | Defecto simulado (lote 2, suite completa) | T21 | Primera prueba que falla | Segundos |
|---|---|---|---|---|
| M23 | el freno de drawdown nunca salta | MUERTO | `test_a_drawdown_past_the_breaker_survives_a_restart` | 39.7 |
| M24 | el freno de drawdown rechaza la señal pero no pone el sistema en modo seguro | MUERTO | `test_drawdown_breach_halts_the_system_not_just_the_signal` | 409.7 |
| M25 | el límite de pérdida diaria nunca bloquea | MUERTO | `test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_resta` | 32.4 |
| M26 | la regla de salida puede aflojar el stop (falta «solo más ajustado») | MUERTO | `test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_an` | 54.6 |
| M27 | el stop puede quedar del otro lado del último cierre | MUERTO | `test_a_stop_stays_a_stop_never_through_the_last_close` | 376.8 |
| M28 | se elige el candidato más flojo en vez del más ajustado | MUERTO | `test_the_tightest_candidate_wins - Assertion...` | 387.8 |
| M29 | sin encogimiento por error estándar | MUERTO | `test_exploration_buys_lessons_in_unproven_buckets_but_never_in_disprov` | 205.6 |
| M30 | un costo desconocido no impide operar | MUERTO | `test_an_incomplete_estimate_never_makes_a_trade_tradeable` | 413.8 |
| M31 | se ignora el techo de la razón de costos | MUERTO | `test_the_cost_ratio_ceiling_refuses_a_trade_that_depends_on_the_cost_m` | 397.9 |
| M32 | HALT_NEW_ORDERS no admite órdenes que reducen (no se puede cerrar ni proteger) | NO_APLICA (aparece 2 veces) | `` | — |
| M32b | HALT_NEW_ORDERS no admite órdenes que reducen (corregido: cadena única) | MUERTO | `test_deadline_and_time_stop_in_the_same_cycle_send_one_exit_and_the_bo` | 111.2 |
| M33 | muestra mínima de 3 en vez de 30 | MUERTO | `test_an_unfilled_limit_entry_expires_and_frees_the_session` | 203.8 |

**Lote 2:** 11 muertos de 12.
