# Acceptance Contract: Facility-aware triathlon planner
Session: triathlon-app-like-runna-20261030-1759 | PRD: prd.md | Status: locked

## Quality Gates
| Gate | Command | Required |
|------|---------|----------|
| tests | `pytest` | yes |
| lint | `ruff check .` | yes |
| typecheck | `mypy src` | yes |
| e2e (v1) | `pytest tests/e2e` | v1 only |

## Acceptance Criteria

### US-001: Constraint model — locations, facilities and slots (v0)

#### AC-001: Accepts a YAML file defining locations, each with facilities (pool, wattbike, treadmill, road bike, gym) and per-facility opening windows (e.g. pool only after 16:00)
- **Method:** unit-test
- **Test:** `test-stubs/test_us_001_constraint_model_locations_facilities_an.py` > test_ac_001_accepts_a_yaml_file_defining_locations_each_with_facilities_
- **Status:** verified
- **Evidence:** `tests/test_us_001_constraint_model_locations_facilities_an.py::test_ac_001_accepts_a_yaml_file_defining_locations_each_with_facilities_` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-002: Accepts a weekly calendar mapping each day to a location and listing available time slots
- **Method:** unit-test
- **Test:** `test-stubs/test_us_001_constraint_model_locations_facilities_an.py` > test_ac_002_accepts_a_weekly_calendar_mapping_each_day_to_a_location_and
- **Status:** verified
- **Evidence:** `tests/test_us_001_constraint_model_locations_facilities_an.py::test_ac_002_accepts_a_weekly_calendar_mapping_each_day_to_a_location_and` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-003: Rejects config with overlapping slots or unknown facility names, with a clear error
- **Method:** unit-test
- **Test:** `test-stubs/test_us_001_constraint_model_locations_facilities_an.py` > test_ac_003_rejects_config_with_overlapping_slots_or_unknown_facility_na
- **Status:** verified
- **Evidence:** `tests/test_us_001_constraint_model_locations_facilities_an.py::test_ac_003_rejects_config_with_overlapping_slots_or_unknown_facility_na` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-004: Supports date-range overrides (holiday block, exam week, travel)
- **Method:** unit-test
- **Test:** `test-stubs/test_us_001_constraint_model_locations_facilities_an.py` > test_ac_004_supports_date_range_overrides_holiday_block_exam_week_travel
- **Status:** verified
- **Evidence:** `tests/test_us_001_constraint_model_locations_facilities_an.py::test_ac_004_supports_date_range_overrides_holiday_block_exam_week_travel` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

### US-002: Load targets and session library (v0)

#### AC-005: Returns weekly minutes per discipline for a sprint or Olympic template given phase (base/build/taper) and available hours
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_002_load_targets_and_session_library.py` > test_ac_005_returns_weekly_minutes_per_discipline_for_a_sprint_or_olympi
- **Status:** verified
- **Evidence:** `tests/test_us_002_load_targets_and_session_library.py::test_ac_005_returns_weekly_minutes_per_discipline_for_a_sprint_or_olympi` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-006: Caps week-on-week load increase at a configurable ramp (default 10%)
- **Method:** unit-test
- **Test:** `test-stubs/test_us_002_load_targets_and_session_library.py` > test_ac_006_caps_week_on_week_load_increase_at_a_configurable_ramp_defau
- **Status:** verified
- **Evidence:** `tests/test_us_002_load_targets_and_session_library.py::test_ac_006_caps_week_on_week_load_increase_at_a_configurable_ramp_defau` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-007: Each session has type, duration, intensity, required facilities, and a Key or Flex flag
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_002_load_targets_and_session_library.py` > test_ac_007_each_session_has_type_duration_intensity_required_facilities
- **Status:** verified
- **Evidence:** `tests/test_us_002_load_targets_and_session_library.py::test_ac_007_each_session_has_type_duration_intensity_required_facilities` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-008: Session library includes indoor substitutes (wattbike for road bike, treadmill for outdoor run)
- **Method:** unit-test
- **Test:** `test-stubs/test_us_002_load_targets_and_session_library.py` > test_ac_008_session_library_includes_indoor_substitutes_wattbike_for_roa
- **Status:** verified
- **Evidence:** `tests/test_us_002_load_targets_and_session_library.py::test_ac_008_session_library_includes_indoor_substitutes_wattbike_for_roa` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

### US-003: Weekly planner (CP-SAT) (v0)

#### AC-009: Never places a session in a slot whose location lacks its required facility or is outside opening hours (hard constraint)
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_003_weekly_planner_cp_sat.py` > test_ac_009_never_places_a_session_in_a_slot_whose_location_lacks_its_re
- **Status:** verified
- **Evidence:** `tests/test_us_003_weekly_planner_cp_sat.py::test_ac_009_never_places_a_session_in_a_slot_whose_location_lacks_its_re` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-010: Never places two hard sessions on consecutive days or a session overlapping another
- **Method:** unit-test
- **Test:** `test-stubs/test_us_003_weekly_planner_cp_sat.py` > test_ac_010_never_places_two_hard_sessions_on_consecutive_days_or_a_sess
- **Status:** verified
- **Evidence:** `tests/test_us_003_weekly_planner_cp_sat.py::test_ac_010_never_places_two_hard_sessions_on_consecutive_days_or_a_sess` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-011: Objective maximises Σ P(complete | slot) × session value
- **Method:** unit-test
- **Test:** `test-stubs/test_us_003_weekly_planner_cp_sat.py` > test_ac_011_objective_maximises_p_complete_slot_session_value
- **Status:** verified
- **Evidence:** `tests/test_us_003_weekly_planner_cp_sat.py::test_ac_011_objective_maximises_p_complete_slot_session_value` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-012: Returns a plan within 10 seconds for a 7-day, 30-slot week
- **Method:** metric
- **Test:** `test-stubs/test_us_003_weekly_planner_cp_sat.py` > test_ac_012_returns_a_plan_within_10_seconds_for_a_7_day_30_slot_week
- **Status:** verified
- **Evidence:** `tests/test_us_003_weekly_planner_cp_sat.py::test_ac_012_returns_a_plan_within_10_seconds_for_a_7_day_30_slot_week` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-013: Returns "infeasible" with the binding constraint named when targets can't fit
- **Method:** unit-test
- **Test:** `test-stubs/test_us_003_weekly_planner_cp_sat.py` > test_ac_013_returns_infeasible_with_the_binding_constraint_named_when_ta
- **Status:** verified
- **Evidence:** `tests/test_us_003_weekly_planner_cp_sat.py::test_ac_013_returns_infeasible_with_the_binding_constraint_named_when_ta` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

### US-004: Logging and adherence model (v0)

#### AC-014: Reads a Google Sheet (or CSV export) log with planned session ID, status, reason code, actual minutes
- **Method:** integration-test
- **Test:** `test-stubs/test_us_004_logging_and_adherence_model.py` > test_ac_014_reads_a_google_sheet_or_csv_export_log_with_planned_session_
- **Status:** verified
- **Evidence:** `tests/test_us_004_logging_and_adherence_model.py::test_ac_014_reads_a_google_sheet_or_csv_export_log_with_planned_session_` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-015: Maintains a Beta-Binomial completion estimate per slot (day × time window × location), starting from a configurable prior
- **Method:** unit-test
- **Test:** `test-stubs/test_us_004_logging_and_adherence_model.py` > test_ac_015_maintains_a_beta_binomial_completion_estimate_per_slot_day_t
- **Status:** verified
- **Evidence:** `tests/test_us_004_logging_and_adherence_model.py::test_ac_015_maintains_a_beta_binomial_completion_estimate_per_slot_day_t` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-016: Treats unlogged sessions as censored, not skipped
- **Method:** unit-test
- **Test:** `test-stubs/test_us_004_logging_and_adherence_model.py` > test_ac_016_treats_unlogged_sessions_as_censored_not_skipped
- **Status:** verified
- **Evidence:** `tests/test_us_004_logging_and_adherence_model.py::test_ac_016_treats_unlogged_sessions_as_censored_not_skipped` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-017: Reports weekly completed ÷ planned hours and flags if logging response rate is below 70%
- **Method:** unit-test
- **Test:** `test-stubs/test_us_004_logging_and_adherence_model.py` > test_ac_017_reports_weekly_completed_planned_hours_and_flags_if_logging_
- **Status:** verified
- **Evidence:** `tests/test_us_004_logging_and_adherence_model.py::test_ac_017_reports_weekly_completed_planned_hours_and_flags_if_logging_` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-018: Stores every completion row with a `source` field (manual / file / garmin_personal)
- **Method:** unit-test
- **Test:** `test-stubs/test_us_004_logging_and_adherence_model.py` > test_ac_018_stores_every_completion_row_with_a_source_field_manual_file_
- **Status:** verified
- **Evidence:** `tests/test_us_004_logging_and_adherence_model.py::test_ac_018_stores_every_completion_row_with_a_source_field_manual_file_` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

### US-005: Stable re-planning and injury substitution (v0)

#### AC-019: Freezes sessions in the next 24 hours unless the athlete flags them
- **Method:** unit-test
- **Test:** `test-stubs/test_us_005_stable_re_planning_and_injury_substituti.py` > test_ac_019_freezes_sessions_in_the_next_24_hours_unless_the_athlete_fla
- **Status:** verified
- **Evidence:** `tests/test_us_005_stable_re_planning_and_injury_substituti.py::test_ac_019_freezes_sessions_in_the_next_24_hours_unless_the_athlete_fla` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-020: Penalises churn: a re-plan moves the fewest sessions needed, and every move carries a reason code
- **Method:** unit-test
- **Test:** `test-stubs/test_us_005_stable_re_planning_and_injury_substituti.py` > test_ac_020_penalises_churn_a_re_plan_moves_the_fewest_sessions_needed_a
- **Status:** verified
- **Evidence:** `tests/test_us_005_stable_re_planning_and_injury_substituti.py::test_ac_020_penalises_churn_a_re_plan_moves_the_fewest_sessions_needed_a` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-021: An injury flag on a discipline (e.g. calf → no running for N days) remaps its load to allowed disciplines and records the shortfall in a per-discipline debt ledger
- **Method:** unit-test
- **Test:** `test-stubs/test_us_005_stable_re_planning_and_injury_substituti.py` > test_ac_021_an_injury_flag_on_a_discipline_e_g_calf_no_running_for_n_day
- **Status:** verified
- **Evidence:** `tests/test_us_005_stable_re_planning_and_injury_substituti.py::test_ac_021_an_injury_flag_on_a_discipline_e_g_calf_no_running_for_n_day` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-022: Two consecutive pain reports freeze that discipline and output a "see a physio" message
- **Method:** unit-test
- **Test:** `test-stubs/test_us_005_stable_re_planning_and_injury_substituti.py` > test_ac_022_two_consecutive_pain_reports_freeze_that_discipline_and_outp
- **Status:** verified
- **Evidence:** `tests/test_us_005_stable_re_planning_and_injury_substituti.py::test_ac_022_two_consecutive_pain_reports_freeze_that_discipline_and_outp` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-023: Every plan version is appended (never overwritten) to a `plan_session_version` table
- **Method:** unit-test
- **Test:** `test-stubs/test_us_005_stable_re_planning_and_injury_substituti.py` > test_ac_023_every_plan_version_is_appended_never_overwritten_to_a_plan_s
- **Status:** verified
- **Evidence:** `tests/test_us_005_stable_re_planning_and_injury_substituti.py::test_ac_023_every_plan_version_is_appended_never_overwritten_to_a_plan_s` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

### US-006: Export and experiment report (v0)

#### AC-024: Exports the week as an .ics file with one event per session (title, duration, location, description)
- **Method:** integration-test
- **Test:** `test-stubs/test_us_006_export_and_experiment_report.py` > test_ac_024_exports_the_week_as_an_ics_file_with_one_event_per_session_t
- **Status:** verified
- **Evidence:** `tests/test_us_006_export_and_experiment_report.py::test_ac_024_exports_the_week_as_an_ics_file_with_one_event_per_session_t` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-025: Exports structured workouts as .FIT files where the session type supports it
- **Method:** integration-test
- **Test:** `test-stubs/test_us_006_export_and_experiment_report.py` > test_ac_025_exports_structured_workouts_as_fit_files_where_the_session_t
- **Status:** verified
- **Evidence:** `tests/test_us_006_export_and_experiment_report.py::test_ac_025_exports_structured_workouts_as_fit_files_where_the_session_t` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-026: Experiment mode alternates facility-aware and time-only weeks on a fixed schedule
- **Method:** unit-test
- **Test:** `test-stubs/test_us_006_export_and_experiment_report.py` > test_ac_026_experiment_mode_alternates_facility_aware_and_time_only_week
- **Status:** verified
- **Evidence:** `tests/test_us_006_export_and_experiment_report.py::test_ac_026_experiment_mode_alternates_facility_aware_and_time_only_week` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

#### AC-027: Weekly report shows completion ratio by week type, by slot, and by discipline
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_006_export_and_experiment_report.py` > test_ac_027_weekly_report_shows_completion_ratio_by_week_type_by_slot_an
- **Status:** verified
- **Evidence:** `tests/test_us_006_export_and_experiment_report.py::test_ac_027_weekly_report_shows_completion_ratio_by_week_type_by_slot_an` (pytest, 30 Oct 2026)
- **Verified-by:** conductor verification sweep

### US-007: 3-minute onboarding to week-1 preview (v1)

#### AC-028: Onboarding asks only: race + date, 5k/10k time, 100m swim pace, FTP (optional), locations with facilities, weekly slots
- **Method:** unit-test
- **Test:** `test-stubs/test_us_007_3_minute_onboarding_to_week_1_preview.py` > test_ac_028_onboarding_asks_only_race_date_5k_10k_time_100m_swim_pace_ft
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-029: Displays a full week-1 plan before any paywall or install prompt
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_007_3_minute_onboarding_to_week_1_preview.py` > test_ac_029_displays_a_full_week_1_plan_before_any_paywall_or_install_pr
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-030: Median onboarding time ≤3 minutes in usability tests (n≥5)
- **Method:** manual-check
- **Test:** `test-stubs/test_us_007_3_minute_onboarding_to_week_1_preview.py` > test_ac_030_median_onboarding_time_3_minutes_in_usability_tests_n_5
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-031: Offers ready-made location profiles (Work week, Work trip, Home, Family holiday)
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_007_3_minute_onboarding_to_week_1_preview.py` > test_ac_031_offers_ready_made_location_profiles_work_week_work_trip_home
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-008: Today card and logging (v1)

#### AC-032: Today card displays today's sessions with Done / Skipped / Moved buttons at thumb height (≥48px targets)
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_008_today_card_and_logging.py` > test_ac_032_today_card_displays_today_s_sessions_with_done_skipped_moved
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-033: Skipped requires exactly one reason tap (No time / Facility closed / Body / Feeling off)
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_008_today_card_and_logging.py` > test_ac_033_skipped_requires_exactly_one_reason_tap_no_time_facility_clo
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-034: An unlogged session triggers one prompt next morning and is never auto-marked skipped
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_008_today_card_and_logging.py` > test_ac_034_an_unlogged_session_triggers_one_prompt_next_morning_and_is_
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-035: Today card works offline and syncs when back online
- **Method:** integration-test
- **Test:** `test-stubs/test_us_008_today_card_and_logging.py` > test_ac_035_today_card_works_offline_and_syncs_when_back_online
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-009: Change receipts and Undo (v1)

#### AC-036: Every automatic change displays a one-line receipt (what moved, why) with Undo
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_009_change_receipts_and_undo.py` > test_ac_036_every_automatic_change_displays_a_one_line_receipt_what_move
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-037: Changes to Key sessions or readiness-driven changes ask for confirmation first
- **Method:** unit-test
- **Test:** `test-stubs/test_us_009_change_receipts_and_undo.py` > test_ac_037_changes_to_key_sessions_or_readiness_driven_changes_ask_for_
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-038: Tomorrow's sessions lock at 21:00 local time
- **Method:** unit-test
- **Test:** `test-stubs/test_us_009_change_receipts_and_undo.py` > test_ac_038_tomorrow_s_sessions_lock_at_21_00_local_time
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-010: Reminders and calendar (v1)

#### AC-039: Provides a subscribable .ics feed URL that updates after every re-plan
- **Method:** integration-test
- **Test:** `test-stubs/test_us_010_reminders_and_calendar.py` > test_ac_039_provides_a_subscribable_ics_feed_url_that_updates_after_ever
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-040: Offers PWA install only after the week-1 preview, with an iOS Add-to-Home-Screen walkthrough
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_010_reminders_and_calendar.py` > test_ac_040_offers_pwa_install_only_after_the_week_1_preview_with_an_ios
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-041: Sends a web push reminder at a user-chosen time before each session (installed PWA only)
- **Method:** integration-test
- **Test:** `test-stubs/test_us_010_reminders_and_calendar.py` > test_ac_041_sends_a_web_push_reminder_at_a_user_chosen_time_before_each_
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-011: Billing (v1)

#### AC-042: Stripe Checkout supports £79.99/yr, £12.99/mo and Founding-250 £59.99/yr, plus USD/EUR equivalents
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_011_billing.py` > test_ac_042_stripe_checkout_supports_79_99_yr_12_99_mo_and_founding_250_
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-043: 14-day trial; cancellation in two taps; no plan is ever stranded within 14 days of a race
- **Method:** unit-test
- **Test:** `test-stubs/test_us_011_billing.py` > test_ac_043_14_day_trial_cancellation_in_two_taps_no_plan_is_ever_strand
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-044: Free off-season mode keeps the account and history after a subscription lapses
- **Method:** unit-test
- **Test:** `test-stubs/test_us_011_billing.py` > test_ac_044_free_off_season_mode_keeps_the_account_and_history_after_a_s
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-045: Trial→paid is tracked by segment (student/adult) and sync method (file/Garmin)
- **Method:** unit-test
- **Test:** `test-stubs/test_us_011_billing.py` > test_ac_045_trial_paid_is_tracked_by_segment_student_adult_and_sync_meth
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-012: Safety, privacy and compliance (v1)

#### AC-046: Rejects sign-up when date of birth gives age under 18
- **Method:** unit-test
- **Test:** `test-stubs/test_us_012_safety_privacy_and_compliance.py` > test_ac_046_rejects_sign_up_when_date_of_birth_gives_age_under_18
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-047: Collects explicit consent for health data (readiness, injury) separately from terms
- **Method:** unit-test
- **Test:** `test-stubs/test_us_012_safety_privacy_and_compliance.py` > test_ac_047_collects_explicit_consent_for_health_data_readiness_injury_s
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-048: User can export all their data (JSON/CSV) and delete their account from settings
- **Method:** unit-test
- **Test:** `test-stubs/test_us_012_safety_privacy_and_compliance.py` > test_ac_048_user_can_export_all_their_data_json_csv_and_delete_their_acc
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-049: Injury input is user-declared only; no copy anywhere claims diagnosis or injury prevention
- **Method:** e2e-test
- **Test:** `test-stubs/test_us_012_safety_privacy_and_compliance.py` > test_ac_049_injury_input_is_user_declared_only_no_copy_anywhere_claims_d
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-050: DPIA written and ICO registration done before beta (manual check)
- **Method:** manual-check
- **Test:** `test-stubs/test_us_012_safety_privacy_and_compliance.py` > test_ac_050_dpia_written_and_ico_registration_done_before_beta_manual_ch
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-013: Garmin integration (behind a flag) (v1)

#### AC-051: Core loop (plan, log, re-plan) works with the Garmin flag off
- **Method:** unit-test
- **Test:** `test-stubs/test_us_013_garmin_integration_behind_a_flag.py` > test_ac_051_core_loop_plan_log_re_plan_works_with_the_garmin_flag_off
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-052: When enabled, pushes only changed sessions to Garmin via the Training API after each re-plan
- **Method:** integration-test
- **Test:** `test-stubs/test_us_013_garmin_integration_behind_a_flag.py` > test_ac_052_when_enabled_pushes_only_changed_sessions_to_garmin_via_the_
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-053: Garmin-sourced activity rows are tagged `garmin_api` and excluded from pooled cross-user estimates
- **Method:** unit-test
- **Test:** `test-stubs/test_us_013_garmin_integration_behind_a_flag.py` > test_ac_053_garmin_sourced_activity_rows_are_tagged_garmin_api_and_exclu
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

#### AC-054: Go/no-go recorded on 1 Sep 2027 based on developer-programme approval
- **Method:** manual-check
- **Test:** `test-stubs/test_us_013_garmin_integration_behind_a_flag.py` > test_ac_054_go_no_go_recorded_on_1_sep_2027_based_on_developer_programme
- **Status:** pending
- **Evidence:** —
- **Verified-by:** —

### US-014: Everyday usability and sane training load (v0)

#### AC-055: Weekly volume starts from what the athlete trains now and ramps from what they actually did; free time is only a ceiling (build +10%, taper −40%) — amended 1 Nov 2026: no target-hours input
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_055_weekly_volume_comes_from_target_hours_not_free_time
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_055_weekly_volume_comes_from_target_hours_not_free_time` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-056: No session exceeds the race-appropriate cap for its kind (e.g. sprint long run ≤ 60')
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_056_no_session_is_longer_than_its_race_appropriate_cap
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_056_no_session_is_longer_than_its_race_appropriate_cap` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-057: A Key session too long for every slot is shortened to the longest slot that can host it, with a note, instead of failing the week
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_057_key_session_too_long_for_every_slot_is_shortened_not_infeasible
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_057_key_session_too_long_for_every_slot_is_shortened_not_infeasible` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-058: After a plan or re-plan the log matches it: unlogged rows follow moves, dropped sessions are removed, logged rows never change
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_058_log_follows_the_plan_without_touching_logged_rows
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_058_log_follows_the_plan_without_touching_logged_rows` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-059: A re-plan keeps earlier sessions in the stored week and only reschedules Key sessions logged as skipped, as Flex catch-ups
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_059_replan_keeps_history_and_only_redoes_skipped_key_sessions
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_059_replan_keeps_history_and_only_redoes_skipped_key_sessions` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-060: `init` builds a valid config from plain answers (no YAML knowledge), and unquoted YAML times like 6:30 load as 06:30
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_060_init_wizard_builds_a_valid_config_from_plain_answers
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_060_init_wizard_builds_a_valid_config_from_plain_answers` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-061: Plain-English inputs: --week this/next, --injury run[:days|:date], --unavailable thu / thu-pm / "thu 16:30" / a date
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_061_plain_english_week_injury_and_slot_inputs
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_061_plain_english_week_injury_and_slot_inputs` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-062: `log` records done/skipped/moved with minutes, reason and pain, by asking one session at a time or in one line
- **Method:** e2e-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_062_log_command_records_sessions_interactively_or_in_one_line
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_062_log_command_records_sessions_interactively_or_in_one_line` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-063: Declared injuries persist across commands, apply when planning a new week, and can be cleared (which also lifts a pain freeze)
- **Method:** unit-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_063_declared_injuries_persist_apply_to_week_and_can_be_cleared
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_063_declared_injuries_persist_apply_to_week_and_can_be_cleared` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-064: `today` shows today's sessions with plain-English instructions, and the phase is picked from the race date
- **Method:** e2e-test
- **Test:** `tests/test_us_014_everyday_usability.py` > test_ac_064_today_shows_sessions_with_instructions_and_phase_from_race_date
- **Status:** verified
- **Evidence:** `tests/test_us_014_everyday_usability.py::test_ac_064_today_shows_sessions_with_instructions_and_phase_from_race_date` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-015: Local web app (v0)

#### AC-065: `tri-plan web` serves Today, Week, Changed, Progress and Setup; with no config the first page is Setup
- **Method:** e2e-test
- **Test:** `tests/test_us_015_local_web_app.py` > test_ac_065_serves_every_page_and_sends_first_run_to_setup
- **Status:** verified
- **Evidence:** `tests/test_us_015_local_web_app.py::test_ac_065_serves_every_page_and_sends_first_run_to_setup` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-066: The setup form creates and edits the config without YAML; bad input is rejected with a reason and the file is left alone; an existing config round-trips unchanged
- **Method:** e2e-test
- **Test:** `tests/test_us_015_local_web_app.py` > test_ac_066_setup_form_writes_a_valid_config_and_rejects_bad_input
- **Status:** verified
- **Evidence:** `tests/test_us_015_local_web_app.py::test_ac_066_setup_form_writes_a_valid_config_and_rejects_bad_input` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-067: Planning a week from the website writes the same plan, .ics, .FIT and log as the CLI, and offers the .ics and a .zip of workouts to download
- **Method:** e2e-test
- **Test:** `tests/test_us_015_local_web_app.py` > test_ac_067_planning_from_the_website_writes_the_same_files_and_offers_downloads
- **Status:** verified
- **Evidence:** `tests/test_us_015_local_web_app.py::test_ac_067_planning_from_the_website_writes_the_same_files_and_offers_downloads` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-068: From Today or Week: Done (minutes, something hurt, another time), Skipped with one reason tap, and Undo
- **Method:** e2e-test
- **Test:** `tests/test_us_015_local_web_app.py` > test_ac_068_log_done_skipped_and_undo_from_the_website
- **Status:** verified
- **Evidence:** `tests/test_us_015_local_web_app.py::test_ac_068_log_done_skipped_and_undo_from_the_website` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-069: "Something's changed" re-plans from ticked slots, a new or cleared injury and flagged sessions, and shows a receipt for every move
- **Method:** e2e-test
- **Test:** `tests/test_us_015_local_web_app.py` > test_ac_069_something_changed_replans_and_shows_a_receipt_per_move
- **Status:** verified
- **Evidence:** `tests/test_us_015_local_web_app.py::test_ac_069_something_changed_replans_and_shows_a_receipt_per_move` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-070: Every form needs the page's secret token, so another website open in your browser can't change your plan or log
- **Method:** unit-test
- **Test:** `tests/test_us_015_local_web_app.py` > test_ac_070_forms_only_accept_posts_from_the_app_itself
- **Status:** verified
- **Evidence:** `tests/test_us_015_local_web_app.py::test_ac_070_forms_only_accept_posts_from_the_app_itself` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-016: Personalised sessions planned into your availability (v0)

#### AC-071: A 5k time, swim CSS (or 400m + 200m time trials), FTP and threshold or max HR give personal run pace, swim pace, bike power and HR zones that don't overlap; missing numbers fall back to effort; impossible numbers are rejected
- **Method:** unit-test
- **Test:** `tests/test_us_016_personalised_training.py` > test_ac_071_fitness_numbers_give_personal_non_overlapping_zones
- **Status:** verified
- **Evidence:** `tests/test_us_016_personalised_training.py::test_ac_071_fitness_numbers_give_personal_non_overlapping_zones` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-072: Base has tempo, sweet-spot and CSS work; build adds threshold Key sessions plus VO2 and a brick; taper keeps short race-pace openers; every 4th week before the race is a lighter recovery week with no hard sessions
- **Method:** unit-test
- **Test:** `tests/test_us_016_personalised_training.py` > test_ac_072_every_phase_has_the_right_quality_work_and_recovery_weeks
- **Status:** verified
- **Evidence:** `tests/test_us_016_personalised_training.py::test_ac_072_every_phase_has_the_right_quality_work_and_recovery_weeks` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-073: Every session is a structured workout (warm-up, main set, cool-down) that adds up to its planned length, with targets from your zones, and the same steps and targets go into the calendar event and the .FIT file
- **Method:** integration-test
- **Test:** `tests/test_us_016_personalised_training.py` > test_ac_073_structured_workouts_with_targets_on_screen_calendar_and_watch
- **Status:** verified
- **Evidence:** `tests/test_us_016_personalised_training.py::test_ac_073_structured_workouts_with_targets_on_screen_calendar_and_watch` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-074: Sessions are fitted into your free slots and aerobic sessions grow into spare slot time up to the week's budget, never past a session's maximum, the next session, or a facility's opening hours; volume grows from what you train now and what you actually did
- **Method:** unit-test
- **Test:** `tests/test_us_016_personalised_training.py` > test_ac_074_availability_drives_the_plan_and_spare_slot_time_is_used
- **Status:** verified
- **Evidence:** `tests/test_us_016_personalised_training.py::test_ac_074_availability_drives_the_plan_and_spare_slot_time_is_used` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-075: Across a real season: no hard session on the same day as a long one, long ride and long run on different days, nothing on race day, and a packed exam week keeps its most valuable sessions instead of failing
- **Method:** e2e-test
- **Test:** `tests/test_us_016_personalised_training.py` > test_ac_075_coaching_rules_hold_across_a_real_season
- **Status:** verified
- **Evidence:** `tests/test_us_016_personalised_training.py::test_ac_075_coaching_rules_hold_across_a_real_season` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-076: The profile page asks for current fitness and shows your zones; each session page shows why, a zone timeline and every step with your targets; the interface uses no emoji
- **Method:** e2e-test
- **Test:** `tests/test_us_016_personalised_training.py` > test_ac_076_profile_and_session_pages_show_personal_targets_without_emoji
- **Status:** verified
- **Evidence:** `tests/test_us_016_personalised_training.py::test_ac_076_profile_and_session_pages_show_personal_targets_without_emoji` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-017: Less logging, season view, moving sessions, the experiment (v0)

#### AC-077: The experiment is switched on from the Profile page: weeks then alternate facility-aware / time-only, test weeks are labelled, and the season shows which is which
- **Method:** e2e-test
- **Test:** `tests/test_us_017_less_logging_season_and_control.py` > test_ac_077_experiment_is_switched_on_from_the_website
- **Status:** verified
- **Evidence:** `tests/test_us_017_less_logging_season_and_control.py::test_ac_077_experiment_is_switched_on_from_the_website` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-078: The season view lists every week to race day with its phase, recovery weeks, holidays and exams, what was planned and done, and the volume the planner is heading for (≤10%/week growth, a ceiling for the distance, never more than free time)
- **Method:** e2e-test
- **Test:** `tests/test_us_017_less_logging_season_and_control.py` > test_ac_078_season_view_shows_the_road_to_race_day
- **Status:** verified
- **Evidence:** `tests/test_us_017_less_logging_season_and_control.py::test_ac_078_season_view_shows_the_road_to_race_day` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-079: You can move a session to any later slot where its kit is open and there's room; the plan, log and files follow, a logged session can't be moved, and breaking a coaching rule is allowed but flagged
- **Method:** e2e-test
- **Test:** `tests/test_us_017_less_logging_season_and_control.py` > test_ac_079_move_a_session_yourself_within_the_rules
- **Status:** verified
- **Evidence:** `tests/test_us_017_less_logging_season_and_control.py::test_ac_079_move_a_session_yourself_within_the_rules` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-080: Activity files (.fit, a .zip export, or a folder) tick off the matching planned session: same sport and week, same day = done, other day = moved; a brick's run leg is merged; extras are reported, not forced in; nothing is imported twice and sessions you logged yourself are left alone
- **Method:** integration-test
- **Test:** `tests/test_us_017_less_logging_season_and_control.py` > test_ac_080_watch_files_tick_off_the_right_sessions_once
- **Status:** verified
- **Evidence:** `tests/test_us_017_less_logging_season_and_control.py::test_ac_080_watch_files_tick_off_the_right_sessions_once` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-081: "Sync from Garmin" uses Garmin's Personal API client with your key from ~/.config/garmin or GARMIN_PERSONAL_API_KEY, downloads recent activities' original files and ticks off sessions; no key or a refused key gives a plain message; the key is stored readable only by you and never in the project
- **Method:** integration-test
- **Test:** `tests/test_us_017_less_logging_season_and_control.py` > test_ac_081_garmin_personal_api_sync
- **Status:** verified
- **Evidence:** `tests/test_us_017_less_logging_season_and_control.py::test_ac_081_garmin_personal_api_sync` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-082: On Today you can sync from Garmin or add activity files; imported sessions show time, distance and heart rate, and you can still say something hurt
- **Method:** e2e-test
- **Test:** `tests/test_us_017_less_logging_season_and_control.py` > test_ac_082_import_from_the_website_and_still_report_pain
- **Status:** verified
- **Evidence:** `tests/test_us_017_less_logging_season_and_control.py::test_ac_082_import_from_the_website_and_still_report_pain` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-018: Strength opt-out, auto-sync, recovery check, Garmin heart rates, effort check (v0)

#### AC-083: Profile lets you opt out of strength sessions; none are planned and their time goes to swim, bike and run, so the week isn't shorter
- **Method:** e2e-test
- **Test:** `tests/test_us_018_garmin_coaching_and_choices.py` > test_ac_083_you_can_opt_out_of_strength_sessions
- **Status:** verified
- **Evidence:** `tests/test_us_018_garmin_coaching_and_choices.py::test_ac_083_you_can_opt_out_of_strength_sessions` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-084: Opening Today syncs with Garmin in the background at most every 30 minutes (activities and this morning's recovery data); the time of the last sync is shown, and a failed sync never breaks the page
- **Method:** e2e-test
- **Test:** `tests/test_us_018_garmin_coaching_and_choices.py` > test_ac_084_opening_the_app_syncs_with_garmin_at_most_every_30_minutes
- **Status:** verified
- **Evidence:** `tests/test_us_018_garmin_coaching_and_choices.py::test_ac_084_opening_the_app_syncs_with_garmin_at_most_every_30_minutes` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-085: The recovery check reads last night's sleep, HRV and resting heart rate from Garmin and applies three plain rules (2+ flags = low, 1 = watch, 0 = good); missing data is "not available", never an alarm
- **Method:** unit-test
- **Test:** `tests/test_us_018_garmin_coaching_and_choices.py` > test_ac_085_recovery_check_reads_sleep_hrv_and_resting_hr
- **Status:** verified
- **Evidence:** `tests/test_us_018_garmin_coaching_and_choices.py::test_ac_085_recovery_check_reads_sleep_hrv_and_resting_hr` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-086: On a low-recovery day with a quality session planned, Today offers to make it easy (same time, place and sport, easy effort); nothing changes unless you press it, and logged or already-easy sessions can't be eased
- **Method:** e2e-test
- **Test:** `tests/test_us_018_garmin_coaching_and_choices.py` > test_ac_086_on_a_low_day_it_offers_to_make_a_hard_session_easy
- **Status:** verified
- **Evidence:** `tests/test_us_018_garmin_coaching_and_choices.py::test_ac_086_on_a_low_day_it_offers_to_make_a_hard_session_easy` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-087: Your threshold, max and resting heart rate can be read from Garmin; they are shown next to your current values and only saved when you tick and confirm, and your zones follow
- **Method:** e2e-test
- **Test:** `tests/test_us_018_garmin_coaching_and_choices.py` > test_ac_087_heart_rates_from_garmin_are_confirmed_before_use
- **Status:** verified
- **Evidence:** `tests/test_us_018_garmin_coaching_and_choices.py::test_ac_087_heart_rates_from_garmin_are_confirmed_before_use` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-088: When your watch's average heart rate for an easy session was above your easy zone, the session says so; hard sessions and sessions without heart rate aren't flagged
- **Method:** e2e-test
- **Test:** `tests/test_us_018_garmin_coaching_and_choices.py` > test_ac_088_effort_check_flags_easy_sessions_done_too_hard
- **Status:** verified
- **Evidence:** `tests/test_us_018_garmin_coaching_and_choices.py::test_ac_088_effort_check_flags_easy_sessions_done_too_hard` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-019: Half distance (v0)

#### AC-089: Half distance is a race option (Profile and init) with bike-heavy splits, more volume (10h default, ramping to a 16h ceiling), a 12-week build, and a clear note that half-iron races need you to be 18
- **Method:** e2e-test
- **Test:** `tests/test_us_019_half_distance.py` > test_ac_089_half_distance_is_a_race_option_with_bigger_training
- **Status:** verified
- **Evidence:** `tests/test_us_019_half_distance.py::test_ac_089_half_distance_is_a_race_option_with_bigger_training` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-090: Half sessions go long-course: long rides up to 4h, long runs up to 2h with fuelling notes, a long brick as a Key build session with a proper run off the bike, and race-pace (tempo) work rather than sprint-style VO2
- **Method:** unit-test
- **Test:** `tests/test_us_019_half_distance.py` > test_ac_090_half_sessions_are_long_course_sessions
- **Status:** verified
- **Evidence:** `tests/test_us_019_half_distance.py::test_ac_090_half_sessions_are_long_course_sessions` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-091: A half week on a school timetable uses double days when it needs to, never two sessions of the same sport in a day (a brick counts as a run), keeps the long ride and long run on different days and puts them at the weekend when the slots allow
- **Method:** e2e-test
- **Test:** `tests/test_us_019_half_distance.py` > test_ac_091_half_weeks_use_double_days_within_the_rules
- **Status:** verified
- **Evidence:** `tests/test_us_019_half_distance.py::test_ac_091_half_weeks_use_double_days_within_the_rules` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-020: Season and plan agree; half workouts are race-specific (v0)

#### AC-092: Planning any week targets the same volume the Season view shows for it (one shared rule); weeks planned far ahead say they assume you complete the weeks before, and a past week you didn't log holds volume flat instead of growing it
- **Method:** e2e-test
- **Test:** `tests/test_us_020_season_agrees_and_half_specific.py` > test_ac_092_planning_a_week_matches_what_season_shows
- **Status:** verified
- **Evidence:** `tests/test_us_020_season_agrees_and_half_specific.py::test_ac_092_planning_a_week_matches_what_season_shows` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-093: Half workouts differ from Olympic ones: race-effort blocks (76–83% FTP) in the long ride, a half-marathon-pace finish to the long run, longer CSS reps, long sweet-spot intervals and a brick that runs at half-marathon effort, with the same targets on the watch
- **Method:** unit-test
- **Test:** `tests/test_us_020_season_agrees_and_half_specific.py` > test_ac_093_half_workouts_are_built_for_the_half
- **Status:** verified
- **Evidence:** `tests/test_us_020_season_agrees_and_half_specific.py::test_ac_093_half_workouts_are_built_for_the_half` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

### US-021: Sessions fit short slots and the week spreads out (v0)

#### AC-094: A session too long for a slot can run there shortened, down to its sensible minimum (a Key session that fits nowhere at all is rescued shorter with a note); full length is used whenever it fits, and the shortened workout still adds up
- **Method:** unit-test
- **Test:** `tests/test_us_021_spread_the_week.py` > test_ac_094_sessions_shrink_to_fit_a_short_slot_but_not_below_their_minimum
- **Status:** verified
- **Evidence:** `tests/test_us_021_spread_the_week.py::test_ac_094_sessions_shrink_to_fit_a_short_slot_but_not_below_their_minimum` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

#### AC-095: On a timetable of short weekday slots and long weekends, weekday slots are used, quality sessions go midweek, the long ride and long run take different weekend days, and no weekend day carries two long sessions or more than its fair share plus the long session
- **Method:** e2e-test
- **Test:** `tests/test_us_021_spread_the_week.py` > test_ac_095_a_school_week_spreads_out_instead_of_piling_onto_the_weekend
- **Status:** verified
- **Evidence:** `tests/test_us_021_spread_the_week.py::test_ac_095_a_school_week_spreads_out_instead_of_piling_onto_the_weekend` (pytest, 1 Nov 2026)
- **Verified-by:** pytest

## Verification Summary
| ID | Criterion | Method | Status | Evidence |
|----|-----------|--------|--------|----------|
| AC-001 | Accepts a YAML file defining locations, each with facilities… | unit-test | verified | test_us_001_constraint_model_locations_facilities_an.py |
| AC-002 | Accepts a weekly calendar mapping each day to a location and… | unit-test | verified | test_us_001_constraint_model_locations_facilities_an.py |
| AC-003 | Rejects config with overlapping slots or unknown facility na… | unit-test | verified | test_us_001_constraint_model_locations_facilities_an.py |
| AC-004 | Supports date-range overrides (holiday block, exam week, tra… | unit-test | verified | test_us_001_constraint_model_locations_facilities_an.py |
| AC-005 | Returns weekly minutes per discipline for a sprint or Olympi… | e2e-test | verified | test_us_002_load_targets_and_session_library.py |
| AC-006 | Caps week-on-week load increase at a configurable ramp (defa… | unit-test | verified | test_us_002_load_targets_and_session_library.py |
| AC-007 | Each session has type, duration, intensity, required facilit… | e2e-test | verified | test_us_002_load_targets_and_session_library.py |
| AC-008 | Session library includes indoor substitutes (wattbike for ro… | unit-test | verified | test_us_002_load_targets_and_session_library.py |
| AC-009 | Never places a session in a slot whose location lacks its re… | e2e-test | verified | test_us_003_weekly_planner_cp_sat.py |
| AC-010 | Never places two hard sessions on consecutive days or a sess… | unit-test | verified | test_us_003_weekly_planner_cp_sat.py |
| AC-011 | Objective maximises Σ P(complete | slot) × session value | unit-test | verified | test_us_003_weekly_planner_cp_sat.py |
| AC-012 | Returns a plan within 10 seconds for a 7-day, 30-slot week | metric | verified | test_us_003_weekly_planner_cp_sat.py |
| AC-013 | Returns "infeasible" with the binding constraint named when … | unit-test | verified | test_us_003_weekly_planner_cp_sat.py |
| AC-014 | Reads a Google Sheet (or CSV export) log with planned sessio… | integration-test | verified | test_us_004_logging_and_adherence_model.py |
| AC-015 | Maintains a Beta-Binomial completion estimate per slot (day … | unit-test | verified | test_us_004_logging_and_adherence_model.py |
| AC-016 | Treats unlogged sessions as censored, not skipped | unit-test | verified | test_us_004_logging_and_adherence_model.py |
| AC-017 | Reports weekly completed ÷ planned hours and flags if loggin… | unit-test | verified | test_us_004_logging_and_adherence_model.py |
| AC-018 | Stores every completion row with a `source` field (manual / … | unit-test | verified | test_us_004_logging_and_adherence_model.py |
| AC-019 | Freezes sessions in the next 24 hours unless the athlete fla… | unit-test | verified | test_us_005_stable_re_planning_and_injury_substituti.py |
| AC-020 | Penalises churn: a re-plan moves the fewest sessions needed,… | unit-test | verified | test_us_005_stable_re_planning_and_injury_substituti.py |
| AC-021 | An injury flag on a discipline (e.g. calf → no running for N… | unit-test | verified | test_us_005_stable_re_planning_and_injury_substituti.py |
| AC-022 | Two consecutive pain reports freeze that discipline and outp… | unit-test | verified | test_us_005_stable_re_planning_and_injury_substituti.py |
| AC-023 | Every plan version is appended (never overwritten) to a `pla… | unit-test | verified | test_us_005_stable_re_planning_and_injury_substituti.py |
| AC-024 | Exports the week as an .ics file with one event per session … | integration-test | verified | test_us_006_export_and_experiment_report.py |
| AC-025 | Exports structured workouts as .FIT files where the session … | integration-test | verified | test_us_006_export_and_experiment_report.py |
| AC-026 | Experiment mode alternates facility-aware and time-only week… | unit-test | verified | test_us_006_export_and_experiment_report.py |
| AC-027 | Weekly report shows completion ratio by week type, by slot, … | e2e-test | verified | test_us_006_export_and_experiment_report.py |
| AC-028 | Onboarding asks only: race + date, 5k/10k time, 100m swim pa… | unit-test | pending | — |
| AC-029 | Displays a full week-1 plan before any paywall or install pr… | e2e-test | pending | — |
| AC-030 | Median onboarding time ≤3 minutes in usability tests (n≥5) | manual-check | pending | — |
| AC-031 | Offers ready-made location profiles (Work week, Work trip, H… | e2e-test | pending | — |
| AC-032 | Today card displays today's sessions with Done / Skipped / M… | e2e-test | pending | — |
| AC-033 | Skipped requires exactly one reason tap (No time / Facility … | e2e-test | pending | — |
| AC-034 | An unlogged session triggers one prompt next morning and is … | e2e-test | pending | — |
| AC-035 | Today card works offline and syncs when back online | integration-test | pending | — |
| AC-036 | Every automatic change displays a one-line receipt (what mov… | e2e-test | pending | — |
| AC-037 | Changes to Key sessions or readiness-driven changes ask for … | unit-test | pending | — |
| AC-038 | Tomorrow's sessions lock at 21:00 local time | unit-test | pending | — |
| AC-039 | Provides a subscribable .ics feed URL that updates after eve… | integration-test | pending | — |
| AC-040 | Offers PWA install only after the week-1 preview, with an iO… | e2e-test | pending | — |
| AC-041 | Sends a web push reminder at a user-chosen time before each … | integration-test | pending | — |
| AC-042 | Stripe Checkout supports £79.99/yr, £12.99/mo and Founding-2… | e2e-test | pending | — |
| AC-043 | 14-day trial; cancellation in two taps; no plan is ever stra… | unit-test | pending | — |
| AC-044 | Free off-season mode keeps the account and history after a s… | unit-test | pending | — |
| AC-045 | Trial→paid is tracked by segment (student/adult) and sync me… | unit-test | pending | — |
| AC-046 | Rejects sign-up when date of birth gives age under 18 | unit-test | pending | — |
| AC-047 | Collects explicit consent for health data (readiness, injury… | unit-test | pending | — |
| AC-048 | User can export all their data (JSON/CSV) and delete their a… | unit-test | pending | — |
| AC-049 | Injury input is user-declared only; no copy anywhere claims … | e2e-test | pending | — |
| AC-050 | DPIA written and ICO registration done before beta (manual c… | manual-check | pending | — |
| AC-051 | Core loop (plan, log, re-plan) works with the Garmin flag of… | unit-test | pending | — |
| AC-052 | When enabled, pushes only changed sessions to Garmin via the… | integration-test | pending | — |
| AC-053 | Garmin-sourced activity rows are tagged `garmin_api` and exc… | unit-test | pending | — |
| AC-054 | Go/no-go recorded on 1 Sep 2027 based on developer-programme… | manual-check | pending | — |
| AC-055 | Weekly volume comes from the athlete's target hours; free ti… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-056 | No session exceeds the race-appropriate cap for its kind (e.… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-057 | A Key session too long for every slot is shortened to the lo… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-058 | After a plan or re-plan the log matches it: unlogged rows fo… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-059 | A re-plan keeps earlier sessions in the stored week and only… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-060 | `init` builds a valid config from plain answers (no YAML kno… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-061 | Plain-English inputs: --week this/next, --injury run[:days|:… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-062 | `log` records done/skipped/moved with minutes, reason and pa… | e2e-test | verified | test_us_014_everyday_usability.py |
| AC-063 | Declared injuries persist across commands, apply when planni… | unit-test | verified | test_us_014_everyday_usability.py |
| AC-064 | `today` shows today's sessions with plain-English instructio… | e2e-test | verified | test_us_014_everyday_usability.py |
| AC-065 | `tri-plan web` serves Today, Week, Changed, Progress and Set… | e2e-test | verified | test_us_015_local_web_app.py |
| AC-066 | The setup form creates and edits the config without YAML; ba… | e2e-test | verified | test_us_015_local_web_app.py |
| AC-067 | Planning a week from the website writes the same plan, .ics,… | e2e-test | verified | test_us_015_local_web_app.py |
| AC-068 | From Today or Week: Done (minutes, something hurt, another t… | e2e-test | verified | test_us_015_local_web_app.py |
| AC-069 | "Something's changed" re-plans from ticked slots, a new or c… | e2e-test | verified | test_us_015_local_web_app.py |
| AC-070 | Every form needs the page's secret token, so another website… | unit-test | verified | test_us_015_local_web_app.py |
| AC-071 | A 5k time, swim CSS (or 400m + 200m time trials), FTP and th… | unit-test | verified | test_us_016_personalised_training.py |
| AC-072 | Base has tempo, sweet-spot and CSS work; build adds threshol… | unit-test | verified | test_us_016_personalised_training.py |
| AC-073 | Every session is a structured workout (warm-up, main set, co… | integration-test | verified | test_us_016_personalised_training.py |
| AC-074 | Sessions are fitted into your free slots and aerobic session… | unit-test | verified | test_us_016_personalised_training.py |
| AC-075 | Across a real season: no hard session on the same day as a l… | e2e-test | verified | test_us_016_personalised_training.py |
| AC-076 | The profile page asks for current fitness and shows your zon… | e2e-test | verified | test_us_016_personalised_training.py |
| AC-077 | The experiment is switched on from the Profile page: weeks t… | e2e-test | verified | test_us_017_less_logging_season_and_control.py |
| AC-078 | The season view lists every week to race day with its phase,… | e2e-test | verified | test_us_017_less_logging_season_and_control.py |
| AC-079 | You can move a session to any later slot where its kit is op… | e2e-test | verified | test_us_017_less_logging_season_and_control.py |
| AC-080 | Activity files (.fit, a .zip export, or a folder) tick off t… | integration-test | verified | test_us_017_less_logging_season_and_control.py |
| AC-081 | "Sync from Garmin" uses Garmin's Personal API client with yo… | integration-test | verified | test_us_017_less_logging_season_and_control.py |
| AC-082 | On Today you can sync from Garmin or add activity files; imp… | e2e-test | verified | test_us_017_less_logging_season_and_control.py |
| AC-083 | Profile lets you opt out of strength sessions; none are plan… | e2e-test | verified | test_us_018_garmin_coaching_and_choices.py |
| AC-084 | Opening Today syncs with Garmin in the background at most ev… | e2e-test | verified | test_us_018_garmin_coaching_and_choices.py |
| AC-085 | The recovery check reads last night's sleep, HRV and resting… | unit-test | verified | test_us_018_garmin_coaching_and_choices.py |
| AC-086 | On a low-recovery day with a quality session planned, Today … | e2e-test | verified | test_us_018_garmin_coaching_and_choices.py |
| AC-087 | Your threshold, max and resting heart rate can be read from … | e2e-test | verified | test_us_018_garmin_coaching_and_choices.py |
| AC-088 | When your watch's average heart rate for an easy session was… | e2e-test | verified | test_us_018_garmin_coaching_and_choices.py |
| AC-089 | Half distance is a race option (Profile and init) with bike-… | e2e-test | verified | test_us_019_half_distance.py |
| AC-090 | Half sessions go long-course: long rides up to 4h, long runs… | unit-test | verified | test_us_019_half_distance.py |
| AC-091 | A half week on a school timetable uses double days when it n… | e2e-test | verified | test_us_019_half_distance.py |
| AC-092 | Planning any week targets the same volume the Season view sh… | e2e-test | verified | test_us_020_season_agrees_and_half_specific.py |
| AC-093 | Half workouts differ from Olympic ones: race-effort blocks (… | unit-test | verified | test_us_020_season_agrees_and_half_specific.py |
| AC-094 | A session too long for a slot can run there shortened, down … | unit-test | verified | test_us_021_spread_the_week.py |
| AC-095 | On a timetable of short weekday slots and long weekends, wee… | e2e-test | verified | test_us_021_spread_the_week.py |

Progress: 68/95 verified — v0 (AC-001–AC-027, AC-055–AC-095) complete; v1 (AC-028–AC-054) pending until the July 2027 gate

GitHub issue: not created — no repository linked to this session.