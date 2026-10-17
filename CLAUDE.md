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
main.py          # Entry point: JohannaApp wires everything, owns save/load flow + update dialogs
version.py       # __version__ + GITHUB_REPO - single source of truth (window title, updater; keep pyproject.toml in sync, workflow enforces it on v* tags)
updater.py       # Auto-update via GitHub releases: check/download threads, robocopy swap script (spares data\); asset name JohannaAssistenten-windows.zip is part of the contract
BESCHREIBUNG.md  # Authoritative German description of purpose & behavior
PLANUNGSLOGIK.md # Schematic of the generator's assignment order & priorities
```

## Architecture & Data Flow

### Core Models (`models/`)
- **holidays.py**: Bavarian public holidays, computed per year (Gauss Easter formula, stdlib only, `lru_cache`d). `holiday_name(year, month, day)` drives the gray weekend-style shading in PlanTab cells, AbsenceTab calendar and the PDF export — display only, the scheduling engine ignores holidays. The on-screen gray is `theme.colors().weekend` (per color scheme); the PDF uses its own neutral print gray.
- **calendar_de.py**: `MONTHS_DE`, `WEEKDAYS_DE`, `month_label(year, month)` ("Oktober 2026") — shared by UI and exports.
- **MonthPlan**: Root container for a month (year, month, schedule dict day→entries, assistants list, `notes` dict day→free-text note)
- **Assistant**: id, name, color, active, constraints
- **ShiftEntry**: assistant_id, shift_type, `locked` (fixed — survives re-roll), `generated` (True = placed by the random generator, shown lighter with a dot; False = set by hand, always survives), `candidate`/`chosen` (candidate mechanics for FULL/ON_CALL: several manual proposals per day, only a chosen one counts — `is_effective(entry)` in `models/shift.py` gates every coverage/target count, incl. exports)
- **ShiftType**: FULL (Tagesdienst, the regular case), HALF_MORNING (UI label "Tag"), HALF_AFTERNOON (UI label "Nacht") — formerly shown as VM/NM; enum/file names unchanged. A day is covered by one FULL or by Tag + Nacht (two people). Half shifts count 0.5 toward targets (`shift_weight()`). Display labels live centrally in `models/shift.py`: `SHIFT_LABELS` (short: VOLL/Tag/Nacht/RB — grid, validator, exports) and `SHIFT_NAMES` (long: menus, legends, color dialog) — never hardcode them.
- **AssistantConstraints**: unavailable_dates, vacation_ranges, blocked_dates/blocked_ranges (shown as **"Wunsch"** = free wishes in the UI, formerly "Block"; field names unchanged), max_consecutive_days (1–7), `min_block_days` (1–7; >1 = assistant travels far and is only scheduled in consecutive blocks), `min_gap_days` (0 = off; hard minimum of free days between two of the person's deployment blocks, duty + on-call combined), `oncall_attach` ("none"/"before"/"after"/"both": on-call block is placed directly adjacent to the duty block; "both" splits the same-length block over both sides via `engine.attach_spans`, so the attached on-call days never exceed the duty block's length), min_shifts/max_shifts (None = auto/fair share), `free_wish_quota` (None = "Alle": every block day is hard like vacation; N = the chronologically first N block days of a month have priority ("Vorrang", never overridden), further ones are "Nachrang" and may be overridden in the conflict stage — vacation is never overridden)
- **SettingsProfile / AssistantSettings** (`models/profile.py`): two cross-month settings templates ("Vorlage 1"/"Vorlage 2") holding per-assistant scheduling settings; applied to the current month's plan via a button in the TeamTab. The month plan file stores its own settings snapshot.

### Scheduling Engine (`scheduling/engine.py`)
`generate(plan, seed, resolver=None)` returns a **`GenerationResult(plan, conflicts)`** and implements the **fix-and-re-roll cycle**:
1. Removes all entries with `generated=True and locked=False` (re-roll); resets `chosen` on unlocked candidates
1b. Picks one feasible candidate per candidate day (duty before block placement, on-call in the on-call phase) via the normal fairness ordering
2. Places consecutive FULL blocks for assistants with `min_block_days > 1`; with `oncall_attach` the equally long ON_CALL block is placed directly before/after (or split over both sides) in the same step — see `attach_spans`
3. Fills remaining days greedily (least-loaded first, seeded RNG): FULL for empty days, the missing half (Tag/Nacht) for half-covered days — assigned to a *different* person
4. Distributes on-call (ON_CALL, one person per day, never on the person's own duty day) so each assistant gets **exactly as many on-call days as (weighted) duty shifts** — equality is required, ±0.5 only for half-shift rounding; a final rebalancing pass moves surplus generated on-call entries to assistants below their target
5. `min_gap_days` is a hard constraint everywhere (including relaxation fallbacks): the generator never places an entry that leaves fewer free days between two of a person's deployment blocks
6. **Conflict stage** (duty and on-call): a day only fillable by overriding someone's *Nachrang* free wish gets filled anyway (proposal: largest wish overhang, then least loaded) and reported as a `Conflict`; `resolver(conflict) -> ConflictOption` replays user decisions on a re-run with the same seed (`ui/conflict_dialog.py` drives this from `PlanTab.generate_schedule`, which always materializes a concrete seed). Vacation, Vorrang wishes and hard limits are never overridden; overridden wishes stay in the constraints (warning + corner marker in the cell).

Manual and locked entries always stay and count toward targets (unchosen candidates never do). `validator.py` returns warnings (uncovered/half-covered days, days without on-call, target deviations, on-call/duty inequality, block-length and min-gap violations, overridden free wishes, candidate days without a choice, double bookings) shown live under the plan grid.

### UI Layer (`ui/`)

**Usability is a hard requirement** (see BESCHREIBUNG.md): comfortable click targets, side-by-side minus/plus buttons instead of tiny spin arrows, readable font — but compact enough that a whole month fits on screen. All sizes **and UI colors** live centrally in **`ui/theme.py`** — never hardcode sizes or colors elsewhere:
- `apply_theme(app, palette, dark)` sets Fusion style, font, `QPalette` and the stylesheet; callable again at runtime (`JohannaApp.set_color_scheme`, menu **Einstellungen → Farbschema**, persisted as `color_palette`/`dark_mode`). `PALETTES` holds 4 palettes (ozean, salbei, sand, lavendel), each with a light and dark `ColorScheme`.
- Read colors at paint/build time via `theme.colors()` (surface, weekend, separator, outside, muted, warning, ...); use `theme.text_on(bg)` for readable text on colored fills and `theme.blend()` for alpha composites. Labels get `setProperty("role", "muted"|"warning")` instead of inline stylesheets; the one prominent action per view gets `QPushButton` `role="primary"` (accent fill). Alternating table rows use `QPalette.AlternateBase` = `theme.stripe(scheme)` (a hint of the accent) — just `setAlternatingRowColors(True)`. Items with explicit backgrounds are rebuilt on a scheme switch (`rebuild_grid`/`refresh_all`).
- `STEPPER_WIDTH`/`DAY_COL_MIN_W` give table columns their width (`TEAM_ROW_HEIGHT`/`TEAM_FONT_PT`/`TEAM_NAME_COL_W` the slightly larger team tables); `NOTE_ICON`, `WISH_MARK` ("/" for Wunsch days; documented alternative: "") are the shared glyphs.

- **MainWindow**: `QTabWidget` with tabs "Dienstplan", "Urlaub und Notizen" and "Team"; `on_close_request` callback (returns False to keep the window open) drives the save/ask flow in `main.py`. Hosts the **ControlBar** (`ui/control_bar.py`) between menu and tabs: an oversized value-control strip showing the last-activated `BigStepper` with huge ▲/▼ buttons and ◀/▶ field navigation (`_steppers_in_current_tab` enumerates targets). A tab may expose `control_bar_widget` (PlanTab: the "Wuerfeln" group) — MainWindow appends it at the right end of the ControlBar (directly above the tab's `top_bar` with month/view) and shows it only while that tab is active. **One month for all tabs**: `MainWindow.month_selector` (tab-row corner, left of the active tab's `top_bar`) is the only month selector; `month_changed` → `JohannaApp.change_month`, which re-syncs the selector to the loaded plan even on failure. Tabs never keep their own month.
- **BigStepper** (`ui/widgets/big_stepper.py`): standard value-entry widget replacing QSpinBox (autorepeat, optional "Auto" text at minimum, `BigStepper.activate_hook` reports the active field to the ControlBar). Use it for any new numeric input.
- **PlanTab**: calendar grid (row = assistant, column = day; two switchable views — wide, or split with the second half below). Editing via **stamp buttons** (Tagesdienst | Tag | Nacht | Rufbereitschaft | Urlaub | Wunsch | Notiz | Fixieren | Loeschen; internal stamp ids `vm`/`nm`/`block` unchanged; the dice group lives in the ControlBar, see MainWindow): active stamp + cell click sets (shift stamps create entries with `locked=True` — stamped = fixed point), same-type click removes; entries of a *different* type are only replaced when the "Ueberschreiben" checkbox (persisted `allow_overwrite`, default off) is enabled. "Loeschen" removes any entry. Multi-select (Ctrl/Shift, `ExtendedSelection`) + right-click menu applies to all selected cells. **Candidates**: stamping FULL/ON_CALL onto a day already manually taken by someone else turns all manual same-type entries into candidates (pale + "?" + dashed border); the dice picks one (`chosen`), right-click "Kandidat fest waehlen" or the Fixieren stamp locks a choice, and removing all but one candidate reverts it to a fixed single entry (`_normalize_candidates`). The "Urlaub" stamp toggles a day in the assistant's absence set via `absence_days`/`set_absence_days` (`models/assistant.py`) — consecutive days normalize into `vacation_ranges`, single days into `unavailable_dates`. **Day notes**: the "Notiz" stamp (or right-click) opens a per-day note dialog (`edit_note`); days with a note show a 📝 icon + tooltip in the day header (`_update_day_headers`) and the note of the selected day appears in `note_label` under the grid. Takes the shared `AppSettings` in its constructor; emits `plan_modified`, `constraints_changed` and `notes_changed` (note dialog). Its `top_bar` only holds the view switch.
- **CellDelegate**: paints cells entirely from plan data via a `plan_provider` callable plus the shared `AppSettings`. **Colors are per entry type, not per assistant**: `settings.entry_colors` (keys FULL/HALF_MORNING/HALF_AFTERNOON/ON_CALL/VACATION/BLOCK) — fixed entries (manual or locked) paint fully opaque, generated-unlocked ones with `GENERATED_ALPHA` transparency + dot; lock glyph = fixed, "U"/`theme.WISH_MARK` in the Urlaub/Wunsch color, weekend/holiday shading (`theme.colors().weekend`, `models/holidays.py`); cell base and text color follow the color scheme (`text_on` of the blended fill). Cells of assistants with an effective entry on a day that has a note additionally paint `theme.NOTE_ICON` bottom-left with the note as tooltip (`helpEvent`). Configurable via **Einstellungen → Farben...** (`ui/color_settings_dialog.py`, defaults in `persistence/migrations.py: DEFAULT_ENTRY_COLORS`); AbsenceTab uses the same Urlaub/Wunsch colors. Assistants have no color in the UI anymore (the stored `Assistant.color` is only used by the Excel export). Do not rely on `QTableWidgetItem` text/background — items only carry `(assistant_id, day)` in UserRole.
- **AbsenceTab** (`ui/absence_tab.py`, tab "Urlaub und Notizen"): owns everything about absences plus the month's notes. Far left a column of helper buttons ("Alle" + one per assistant; click = only this person, Ctrl+click = add/remove, at least one stays selected; `_selected_ids`) — everything shown and stamped applies to the selected helpers. Next a week-shaped month calendar (7 columns Mo–So, rows = ISO weeks) of the *plan's* month, painted from the constraints — one person: green = Urlaub / light brown = Wunsch; several: names listed per day (`U`/`W`); 📝 on days with a note. Stamps Urlaub | Wunsch | Loeschen work like the plan grid (click toggles, Ctrl/Shift multi-select + right-click menu) for all selected helpers (`apply_stamp(stamp, days, assistants)`: if all have it → remove from all, else set for all). Right (narrower, stretch 2:1) a `QTabWidget`: "Abwesenheiten" (list filters "Nur dieser Monat"/"Vergangene anzeigen" on top, chronological list of the selected helpers — ranges *and* single days, add/edit/remove dialogs; clicking an entry in another month emits `month_change_requested` deferred via `QTimer`, `refresh_list` keeps the selection) and "Notizen" (**NotesPanel**, `ui/notes_panel.py`: all days of the month; a **single click** in the note column edits inline — `_InlineNoteDelegate`, edit trigger `CurrentChanged`, multi-line notes shown/edited with `LINE_MARK` "⏎"; programmatic selection goes to the day column so no editor pops up; multi-line editor below; "Alle kopieren" to clipboard, "Exportieren..."). Calendar click without stamp selects the day in the notes list, double-click jumps into the editor. No `top_bar`. Emits `absences_changed`, `notes_changed`, `month_change_requested`, `notes_export_requested`.
- **TeamTab**: helper roster plus a two-tab widget ("Vorlage 1"/"Vorlage 2"); "▲ Hoch"/"▼ Runter" buttons reorder the selected assistant (`move_assistant`) — the order of `plan.assistants` is the row order everywhere (grid, exports) and persists as JSON array order, no format change. One settings table per template with inline `BigStepper`s for max/min shifts, max-consecutive, min-block (pairs kept mutually consistent), min-gap ("Abstand"), free-wish quota ("Freiwuensche", "Alle" = None) and an "RB anhaengen" combo. **Max columns sit left of their Min counterpart** (max clamps min, so it must be set first) — same order in `PlanTab`. Tables: no color column (name is column 0, `COL_NAME`), alternating rows, larger rows/font. Template edits do **not** touch the plan; the single `role="primary"` button "Vorlage N in Dienstplan <Monat> uebernehmen" (top row, centered via a 3-column grid whose outer columns get equal minimum width, applies the *visible* template) copies it into the current month's constraints (`apply_profile`). Name edits apply immediately and are mirrored between both tables. No absences here — they moved to the AbsenceTab. Cross-tab sync (wired in `main.py`): `TeamTab.assistants_changed` → `PlanTab.rebuild_grid` + `AbsenceTab.refresh_all`; `TeamTab.profiles_changed` → `mark_modified`; `PlanTab.constraints_changed` → `TeamTab.refresh_all` + `AbsenceTab.refresh_all`; `AbsenceTab.absences_changed` → `PlanTab.refresh_display` + `mark_modified`; `AbsenceTab.notes_changed` → `PlanTab.refresh_display` + `mark_modified`; `PlanTab.notes_changed` → `AbsenceTab.refresh_notes`; `MainWindow.month_selector.month_changed` and `AbsenceTab.month_change_requested` → `JohannaApp.change_month`; `AbsenceTab.notes_export_requested` → `JohannaApp.export_notes`.

Month switching goes through `JohannaApp.change_month`: saves the current month, then loads the target month (never clears silently).

### Persistence (`persistence/`)
Three JSON files under `data/` (next to the executable when frozen — see `_base_dir()`):
- `team.json` — team roster + cross-month constraints (absences, scheduling defaults) + the two settings profiles ("Vorlagen")
- `plans/plan_YYYY_MM.json` — per-month schedule + day notes (`notes`) + per-assistant settings snapshot (`settings`: min/max shifts, max-consecutive, min-block, min-gap, oncall_attach, free_wish_quota)
- `settings.json` — app state: last opened month, window geometry, allow-overwrite flag, seed, `entry_colors` (per-entry-type colors), `skipped_version` (release tag skipped in the startup update prompt), `color_palette`/`dark_mode` (UI color scheme; v6 also migrated the old default red Wunsch color `#E57373` to light brown, custom colors stay), `last_app_version` (see backups)

**Program vs. data**: the release ZIP has no `data\` folder and the updater's robocopy excludes it, so a new version can simply be copied over the program folder. **Backups** (`persistence/backup.py`): when `settings.last_app_version != __version__` at startup, `JohannaApp._backup_on_version_change` copies all data JSON files to `data/sicherungen/<stamp>_v<old>_vor_v<new>/` *before* anything is saved/migrated (keeps the last 10; failure never blocks the start; `data/sicherungen/` is git-ignored). "Datei > Datensicherung erstellen..." saves, then zips `data/` (`create_backup_zip`) to a chosen folder.

"Datei > Speichern unter..." additionally writes a free-standing full-plan copy (schedule + team, `json_store.save`) anywhere; loadable via "Plan-Datei oeffnen...".

**Format versioning & migration** (`migrations.py`): every file carries a `version`. Loaders migrate old files stepwise to the current version. **If you change a file format: bump the `CURRENT_*_VERSION`, add a migration step, and tolerate missing fields with defaults.** Old data must keep working after every release — this is a hard requirement.

**Never write JSON directly** — all reads/writes go through `atomic_io.py`: `write_json` writes a `.tmp`, keeps the previous file as `.bak`, then `os.replace`s it into place (a crash mid-save can no longer destroy the last good state); `read_json` falls back to the `.bak` copy and reports it via `pop_recoveries()`, or raises `DataFileError` if both are broken. A `DataFileError` on team/plan data must **abort the start** (`JohannaApp._abort_on_broken_file`) rather than continue with empty data, which would overwrite the damaged file.

**Saving** (`main.py`): autosave every `AUTOSAVE_INTERVAL_MS` (15 s, only when `is_modified`), plus on month change, on Ctrl+S, on close, and on SIGTERM/SIGINT (a 300 ms idle `QTimer` lets Python signal handlers run inside the Qt loop). Closing with unsaved changes asks Speichern/Verwerfen/Abbrechen via `MainWindow.on_close_request` (returning False keeps the window open). Save errors surface as a dialog once per session and in the status bar; `is_modified` stays set.

### Export Layer (`export/`)
CSVExporter (flat tables), ExcelExporter (openpyxl, assistant colors), PDFExporter (reportlab, **A4 portrait**; takes the shared `AppSettings` as third argument and uses the grid's `entry_colors` — but **all entries uniformly opaque** (fixed vs. in-planning is irrelevant for the printout, not in the legend), weekend/holiday gray — and shows **only duties and on-call, never Urlaub/Wunsch** (confidential, the printout is for the team). Page 1 = both month halves stacked (row height adapts to team size); note days get a highlighted header + framed column + a yellow "Notiz" tag (`backColor`, dark text — readable on every entry color) in each active person's cell; page 2 = notes, summary, adjusted legend, holidays). Notes exporter (`export/notes_exporter.py`: `notes_text(plan)`, `export_notes(plan, folder)` → `notizen_JJJJ_MM.txt`, helpers `month_notes`/`day_label`/`day_staff` shared with the PDF and NotesPanel). New exporters: implement `export(plan, folder)` (pass `settings` too if colors are needed), wire into the menu in `main.py`.

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
