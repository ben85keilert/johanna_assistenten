# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Johanna Assistenten** is a PySide6 (Qt for Python) desktop application for scheduling assistants across a month. Johanna is a person receiving 24/7 personal assistance from a small team; the app fairly distributes the days of a month across that team under per-assistant constraints.

**`BESCHREIBUNG.md` is the authoritative description of purpose and intended behavior** — read it first; new features must align with it (and concept changes update it first).

The application is German-localized and uses JSON for persistence.

## Running & Development

The project is managed with **uv** (`pyproject.toml` + `uv.lock`, venv in `.venv\`,
Python version pinned in `.python-version`).

```bash
uv sync                             # create .venv and install dependencies
uv run main.py                      # run the app
uv sync --group build               # additionally install PyInstaller
```

Windows builds: see README (PyInstaller on Windows, or the `build-windows.yml` GitHub Actions workflow, triggered manually or by `v*` tags).

### Project Structure
```
models/          # Data structures: MonthPlan, Assistant, ShiftEntry, Constraints
scheduling/      # Random generator engine + validator
ui/              # PySide6/Qt UI components and dialogs
persistence/     # JSON save/load, app settings, format migrations
export/          # CSV, Excel, PDF exporters
main.py          # Entry point: JohannaApp wires everything, owns save/load flow
BESCHREIBUNG.md  # Authoritative German description of purpose & behavior
PLANUNGSLOGIK.md # Schematic of the generator's assignment order & priorities
```

## Architecture & Data Flow

### Core Models (`models/`)
- **MonthPlan**: Root container for a month (year, month, schedule dict day→entries, assistants list, `notes` dict day→free-text note)
- **Assistant**: id, name, color, active, constraints
- **ShiftEntry**: assistant_id, shift_type, `locked` (fixed — survives re-roll), `generated` (True = placed by the random generator, shown lighter with a dot; False = set by hand, always survives), `candidate`/`chosen` (candidate mechanics for FULL/ON_CALL: several manual proposals per day, only a chosen one counts — `is_effective(entry)` in `models/shift.py` gates every coverage/target count, incl. exports)
- **ShiftType**: FULL (Tagesdienst, the regular case), HALF_MORNING (VM), HALF_AFTERNOON (NM). A day is covered by one FULL or by VM + NM (two people). Half shifts count 0.5 toward targets (`shift_weight()`).
- **AssistantConstraints**: unavailable_dates, vacation_ranges, blocked_dates/blocked_ranges, max_consecutive_days (1–7), `min_block_days` (1–7; >1 = assistant travels far and is only scheduled in consecutive blocks), `min_gap_days` (0 = off; hard minimum of free days between two of the person's deployment blocks, duty + on-call combined), `oncall_attach` ("none"/"before"/"after"/"both": on-call block is placed directly adjacent to the duty block; "both" splits the same-length block over both sides via `engine.attach_spans`, so the attached on-call days never exceed the duty block's length), min_shifts/max_shifts (None = auto/fair share), `free_wish_quota` (None = "Alle": every block day is hard like vacation; N = the chronologically first N block days of a month have priority ("Vorrang", never overridden), further ones are "Nachrang" and may be overridden in the conflict stage — vacation is never overridden)
- **SettingsProfile / AssistantSettings** (`models/profile.py`): two cross-month settings templates ("Vorlage 1"/"Vorlage 2") holding per-assistant scheduling settings; applied to the current month's plan via a button in the TeamTab. The month plan file stores its own settings snapshot.

### Scheduling Engine (`scheduling/engine.py`)
`generate(plan, seed, resolver=None)` returns a **`GenerationResult(plan, conflicts)`** and implements the **fix-and-re-roll cycle**:
1. Removes all entries with `generated=True and locked=False` (re-roll); resets `chosen` on unlocked candidates
1b. Picks one feasible candidate per candidate day (duty before block placement, on-call in the on-call phase) via the normal fairness ordering
2. Places consecutive FULL blocks for assistants with `min_block_days > 1`; with `oncall_attach` the equally long ON_CALL block is placed directly before/after (or split over both sides) in the same step — see `attach_spans`
3. Fills remaining days greedily (least-loaded first, seeded RNG): FULL for empty days, the missing half (VM/NM) for half-covered days — assigned to a *different* person
4. Distributes on-call (ON_CALL, one person per day, never on the person's own duty day) so each assistant gets **exactly as many on-call days as (weighted) duty shifts** — equality is required, ±0.5 only for half-shift rounding; a final rebalancing pass moves surplus generated on-call entries to assistants below their target
5. `min_gap_days` is a hard constraint everywhere (including relaxation fallbacks): the generator never places an entry that leaves fewer free days between two of a person's deployment blocks
6. **Conflict stage** (duty and on-call): a day only fillable by overriding someone's *Nachrang* free wish gets filled anyway (proposal: largest wish overhang, then least loaded) and reported as a `Conflict`; `resolver(conflict) -> ConflictOption` replays user decisions on a re-run with the same seed (`ui/conflict_dialog.py` drives this from `PlanTab.generate_schedule`, which always materializes a concrete seed). Vacation, Vorrang wishes and hard limits are never overridden; overridden wishes stay in the constraints (warning + corner marker in the cell).

Manual and locked entries always stay and count toward targets (unchosen candidates never do). `validator.py` returns warnings (uncovered/half-covered days, days without on-call, target deviations, on-call/duty inequality, block-length and min-gap violations, overridden free wishes, candidate days without a choice, double bookings) shown live under the plan grid.

### UI Layer (`ui/`)

**Usability is a hard requirement** (see BESCHREIBUNG.md): comfortable click targets, side-by-side minus/plus buttons instead of tiny spin arrows, readable font — but compact enough that a whole month fits on screen. All sizes live centrally in **`ui/theme.py`** (`apply_theme(app)` sets font + stylesheet, and `STEPPER_WIDTH`/`DAY_COL_MIN_W` give table columns their width) — never hardcode sizes elsewhere.

- **MainWindow**: `QTabWidget` with tabs "Dienstplan", "Urlaub" and "Team"; `on_close_request` callback (returns False to keep the window open) drives the save/ask flow in `main.py`. Hosts the **ControlBar** (`ui/control_bar.py`) between menu and tabs: an oversized value-control strip showing the last-activated `BigStepper` with huge ▲/▼ buttons and ◀/▶ field navigation (`_steppers_in_current_tab` enumerates targets).
- **BigStepper** (`ui/widgets/big_stepper.py`): standard value-entry widget replacing QSpinBox (autorepeat, optional "Auto" text at minimum, `BigStepper.activate_hook` reports the active field to the ControlBar). Use it for any new numeric input.
- **PlanTab**: calendar grid (row = assistant, column = day; two switchable views — wide, or split with the second half below). Editing via **stamp buttons** (Tagesdienst | VM | NM | Rufbereitschaft | Urlaub | Block | Notiz | Fixieren | Loeschen): active stamp + cell click sets (shift stamps create entries with `locked=True` — stamped = fixed point), same-type click removes; entries of a *different* type are only replaced when the "Ueberschreiben" checkbox (persisted `allow_overwrite`, default off) is enabled. "Loeschen" removes any entry. Multi-select (Ctrl/Shift, `ExtendedSelection`) + right-click menu applies to all selected cells. **Candidates**: stamping FULL/ON_CALL onto a day already manually taken by someone else turns all manual same-type entries into candidates (pale + "?" + dashed border); the dice picks one (`chosen`), right-click "Kandidat fest waehlen" or the Fixieren stamp locks a choice, and removing all but one candidate reverts it to a fixed single entry (`_normalize_candidates`). The "Urlaub" stamp toggles a day in the assistant's absence set via `absence_days`/`set_absence_days` (`models/assistant.py`) — consecutive days normalize into `vacation_ranges`, single days into `unavailable_dates`. **Day notes**: the "Notiz" stamp (or right-click) opens a per-day note dialog (`edit_note`); days with a note show a 📝 icon + tooltip in the day header (`_update_day_headers`) and the note of the selected day appears in `note_label` under the grid. Takes the shared `AppSettings` in its constructor; emits `plan_modified`, `constraints_changed`, and `month_change_requested`.
- **CellDelegate**: paints cells entirely from plan data via a `plan_provider` callable plus the shared `AppSettings`. **Colors are per entry type, not per assistant**: `settings.entry_colors` (keys FULL/HALF_MORNING/HALF_AFTERNOON/ON_CALL/VACATION/BLOCK) — fixed entries (manual or locked) paint fully opaque, generated-unlocked ones with `GENERATED_ALPHA` transparency + dot; lock glyph = fixed, "U"/"X" in the Urlaub/Block color, weekend shading. Configurable via **Einstellungen → Farben...** (`ui/color_settings_dialog.py`, defaults in `persistence/migrations.py: DEFAULT_ENTRY_COLORS`); AbsenceTab uses the same Urlaub/Block colors. Assistant colors remain for lists/combos/exports only. Do not rely on `QTableWidgetItem` text/background — items only carry `(assistant_id, day)` in UserRole.
- **AbsenceTab** (`ui/absence_tab.py`, tab "Urlaub"): owns everything about absences. Left a week-shaped month calendar (7 columns Mo–So, rows = ISO weeks) painted from the constraints — green = Urlaub, red = Block, names listed per day in the "Alle Helfer" view; stamps Urlaub | Block | Loeschen work like the plan grid (click toggles, Ctrl/Shift multi-select + right-click menu), always for the person picked in the tab-row bar. Right the chronological absence list (ranges *and* single days, add/edit/remove dialogs). Month and person live in its own `top_bar`, independent of the plan's month. Emits `absences_changed`.
- **TeamTab**: helper roster plus a two-tab widget ("Vorlage 1"/"Vorlage 2"); "▲ Hoch"/"▼ Runter" buttons reorder the selected assistant (`move_assistant`) — the order of `plan.assistants` is the row order everywhere (grid, exports) and persists as JSON array order, no format change. One settings table per template with inline `BigStepper`s for max/min shifts, max-consecutive, min-block (pairs kept mutually consistent), min-gap ("Abstand"), free-wish quota ("Freiwuensche", "Alle" = None) and an "RB anhaengen" combo. **Max columns sit left of their Min counterpart** (max clamps min, so it must be set first) — same order in `PlanTab`. Template edits do **not** touch the plan; the "In Dienstplan … uebernehmen" button copies the template into the current month's constraints (`apply_profile`). Name/color edits apply immediately and are mirrored between both tables. No absences here — they moved to the AbsenceTab. Cross-tab sync (wired in `main.py`): `TeamTab.assistants_changed` → `PlanTab.rebuild_grid` + `AbsenceTab.refresh_all`; `TeamTab.profiles_changed` → `mark_modified`; `PlanTab.constraints_changed` → `TeamTab.refresh_all` + `AbsenceTab.refresh_all`; `AbsenceTab.absences_changed` → `PlanTab.refresh_display` + `mark_modified`.

Month switching goes through `JohannaApp.change_month`: saves the current month, then loads the target month (never clears silently).

### Persistence (`persistence/`)
Three JSON files under `data/` (next to the executable when frozen — see `_base_dir()`):
- `team.json` — team roster + cross-month constraints (absences, scheduling defaults) + the two settings profiles ("Vorlagen")
- `plans/plan_YYYY_MM.json` — per-month schedule + day notes (`notes`) + per-assistant settings snapshot (`settings`: min/max shifts, max-consecutive, min-block, min-gap, oncall_attach, free_wish_quota)
- `settings.json` — app state: last opened month, window geometry, allow-overwrite flag, seed, `entry_colors` (per-entry-type colors)

"Datei > Speichern unter..." additionally writes a free-standing full-plan copy (schedule + team, `json_store.save`) anywhere; loadable via "Plan-Datei oeffnen...".

**Format versioning & migration** (`migrations.py`): every file carries a `version`. Loaders migrate old files stepwise to the current version. **If you change a file format: bump the `CURRENT_*_VERSION`, add a migration step, and tolerate missing fields with defaults.** Old data must keep working after every release — this is a hard requirement.

**Never write JSON directly** — all reads/writes go through `atomic_io.py`: `write_json` writes a `.tmp`, keeps the previous file as `.bak`, then `os.replace`s it into place (a crash mid-save can no longer destroy the last good state); `read_json` falls back to the `.bak` copy and reports it via `pop_recoveries()`, or raises `DataFileError` if both are broken. A `DataFileError` on team/plan data must **abort the start** (`JohannaApp._abort_on_broken_file`) rather than continue with empty data, which would overwrite the damaged file.

**Saving** (`main.py`): autosave every `AUTOSAVE_INTERVAL_MS` (15 s, only when `is_modified`), plus on month change, on Ctrl+S, on close, and on SIGTERM/SIGINT (a 300 ms idle `QTimer` lets Python signal handlers run inside the Qt loop). Closing with unsaved changes asks Speichern/Verwerfen/Abbrechen via `MainWindow.on_close_request` (returning False keeps the window open). Save errors surface as a dialog once per session and in the status bar; `is_modified` stays set.

### Export Layer (`export/`)
CSVExporter (flat tables), ExcelExporter (openpyxl, assistant colors), PDFExporter (reportlab, landscape). New exporters: implement `export(plan, folder)`, wire into the menu in `main.py`.

## Key Design Decisions

1. **Fix-and-re-roll workflow**: users hand-place fixed points, generate, lock what they like, re-roll the rest. Generated entries are visually distinct.
2. **Greedy algorithm**: simple and predictable; intentionally not an optimal solver.
3. **Seeded RNG** for reproducible schedules.
4. **Dataclasses** for all models; explicit dict (de)serialization helpers in `json_store.py`.
5. **Constraints live per assistant**; absences are cross-month in team.json, scheduling settings are snapshotted per month in the plan file (and prepared/applied via the two team-tab templates).
6. **Data confidentiality**: repo `data/` contains dummy data only (deliberately versioned as examples). Real personal data must never be committed.

## Common Tasks

### Add a New Constraint
1. Add field to `AssistantConstraints` in `models/assistant.py`
2. Serialize in `persistence/json_store.py` (`_constraints_to_dict`/`_constraints_from_dict`) **and add a format migration** in `persistence/migrations.py`
3. Respect it in `scheduling/engine.py` and warn in `scheduling/validator.py`
4. Add UI input to `TeamTab` (inline `BigStepper` column) or a stamp in `PlanTab`
5. Document it in `BESCHREIBUNG.md`

### Extend the UI
Tabs live in `MainWindow.tab_widget`; create a `QWidget` subclass, instantiate in `JohannaApp.__init__`, add via `set_*_tab`/`addTab`.

## German Localization Notes

All UI strings, labels, and messages are in German. This is deliberate. Maintain German throughout (ASCII umlaut spellings like "ue" are used in code strings).

## State Management

**Single Source of Truth**: `JohannaApp.plan` (a `MonthPlan`) is the canonical schedule state; the shared `AppSettings` instance is the canonical settings state. UI components read/write these objects and emit signals; `MainWindow.is_modified` tracks unsaved changes (set via `mark_modified`, cleared on save; autosave on close makes this mostly informational).

## Testing Notes

No formal test suite. For headless smoke tests use `QT_QPA_PLATFORM=offscreen` and drive `JohannaApp`/`PlanTab` directly (see git history for examples). The engine and persistence layers are plain Python and easy to test without Qt.

## Future Direction (noted, not implemented)

Server-based operation where assistants log in and enter their own vacations/free days themselves.
