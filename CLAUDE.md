# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Johanna Assistenten** is a PySide6 (Qt for Python) desktop application for scheduling assistants across a month. Johanna is a person receiving 24/7 personal assistance from a small team; the app fairly distributes the days of a month across that team under per-assistant constraints.

**`BESCHREIBUNG.md` is the authoritative description of purpose and intended behavior** — read it first; new features must align with it (and concept changes update it first).

The application is German-localized and uses JSON for persistence.

## Running & Development

```bash
python main.py                      # run the app
pip install -r requirements.txt     # install dependencies
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
```

## Architecture & Data Flow

### Core Models (`models/`)
- **MonthPlan**: Root container for a month (year, month, schedule dict day→entries, assistants list)
- **Assistant**: id, name, color, active, constraints
- **ShiftEntry**: assistant_id, shift_type, `locked` (fixed — survives re-roll), `generated` (True = placed by the random generator, shown lighter with a dot; False = set by hand, always survives)
- **ShiftType**: FULL (Tagesdienst, the regular case), HALF_MORNING (VM), HALF_AFTERNOON (NM). A day is covered by one FULL or by VM + NM (two people). Half shifts count 0.5 toward targets (`shift_weight()`).
- **AssistantConstraints**: unavailable_dates, vacation_ranges, max_consecutive_days (1–7), `min_block_days` (1–7; >1 = assistant travels far and is only scheduled in consecutive blocks), target_shifts (None = auto/fair share)

### Scheduling Engine (`scheduling/engine.py`)
`generate(plan, seed)` implements the **fix-and-re-roll cycle**:
1. Removes all entries with `generated=True and locked=False` (re-roll)
2. Places consecutive FULL blocks for assistants with `min_block_days > 1`
3. Fills remaining days greedily (least-loaded first, seeded RNG): FULL for empty days, the missing half (VM/NM) for half-covered days — assigned to a *different* person

Manual and locked entries always stay and count toward targets. `validator.py` returns warnings (uncovered/half-covered days, target deviations, block-length violations) shown live under the plan grid.

### UI Layer (`ui/`)
- **MainWindow**: `QTabWidget` with tabs "Dienstplan" and "Team"; `on_close_save` callback triggers autosave in `main.py`
- **PlanTab**: calendar grid (row = assistant, column = day). Editing via **stamp buttons** (Tagesdienst | VM | NM | Urlaub | Fixieren): active stamp + cell click sets, same-click removes, overwrite asks (toggleable, persisted). Multi-select (Ctrl/Shift, `ExtendedSelection`) + right-click menu applies to all selected cells. The "Urlaub" stamp writes to `constraints.unavailable_dates`. Takes the shared `AppSettings` in its constructor; emits `plan_modified` and `month_change_requested`.
- **CellDelegate**: paints cells entirely from plan data via a `plan_provider` callable (assistant color, lighter + dot = generated, lock glyph = fixed, gray "U" = unavailable/vacation, weekend shading). Do not rely on `QTableWidgetItem` text/background — items only carry `(assistant_id, day)` in UserRole.
- **TeamTab / ConstraintsDialog**: manage assistants and constraints (incl. "Min. Tage am Stueck"; dialog validates min_block ≤ max_consecutive)

Month switching goes through `JohannaApp.change_month`: saves the current month, then loads the target month (never clears silently).

### Persistence (`persistence/`)
Three JSON files under `data/` (next to the executable when frozen — see `_base_dir()`):
- `team.json` — team roster (cross-month)
- `plans/plan_YYYY_MM.json` — per-month schedule + per-assistant constraints
- `settings.json` — app state: last opened month, window geometry, confirm-overwrite flag, seed

**Format versioning & migration** (`migrations.py`): every file carries a `version`. Loaders migrate old files stepwise to the current version. **If you change a file format: bump the `CURRENT_*_VERSION`, add a migration step, and tolerate missing fields with defaults.** Old data must keep working after every release — this is a hard requirement.

App saves automatically on close and restores the last state on start.

### Export Layer (`export/`)
CSVExporter (flat tables), ExcelExporter (openpyxl, assistant colors), PDFExporter (reportlab, landscape). New exporters: implement `export(plan, folder)`, wire into the menu in `main.py`.

## Key Design Decisions

1. **Fix-and-re-roll workflow**: users hand-place fixed points, generate, lock what they like, re-roll the rest. Generated entries are visually distinct.
2. **Greedy algorithm**: simple and predictable; intentionally not an optimal solver.
3. **Seeded RNG** for reproducible schedules.
4. **Dataclasses** for all models; explicit dict (de)serialization helpers in `json_store.py`.
5. **Constraints live per assistant** and are stored per month in the plan file (team.json holds only roster data).
6. **Data confidentiality**: repo `data/` contains dummy data only (deliberately versioned as examples). Real personal data must never be committed.

## Common Tasks

### Add a New Constraint
1. Add field to `AssistantConstraints` in `models/assistant.py`
2. Serialize in `persistence/json_store.py` (`_constraints_to_dict`/`_constraints_from_dict`) **and add a format migration** in `persistence/migrations.py`
3. Respect it in `scheduling/engine.py` and warn in `scheduling/validator.py`
4. Add UI input to `ConstraintsDialog`; optionally a column in `TeamTab`
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
