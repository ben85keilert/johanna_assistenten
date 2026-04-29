# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Johanna Assistenten** is a complete PySide6 (Qt for Python) desktop application for scheduling assistants across a month with multiple constraints. The MVP includes all core features: team management, interactive scheduling with constraints, automatic plan generation using a greedy algorithm, and exports (CSV, Excel, PDF).

The application is German-localized and uses JSON for persistence.

## Running & Development

### Run the Application
```bash
python main.py
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Project Structure
```
models/          # Data structures: MonthPlan, Assistant, Shift, Constraints
scheduling/      # Greedy algorithm engine + constraint validator
ui/              # PySide6/Qt UI components and dialogs
persistence/     # JSON save/load logic
export/          # CSV, Excel, PDF exporters
main.py          # Entry point: JohannaApp class instantiates and wires everything
```

## Architecture & Data Flow

### Core Models (`models/`)
- **MonthPlan**: Root container for a month's schedule (year, month, schedule dict, assistants list)
- **Assistant**: Team member with ID, name, color, and constraints
- **ShiftEntry**: A single shift assignment (day, assistant_id, shift_type, locked status)
- **ShiftType**: Enum (VOLL=24h, VM=morning, NM=evening)
- **AssistantConstraints**: Per-assistant rules (unavailable dates, vacation ranges, max consecutive days, target shifts)

### Scheduling Engine (`scheduling/engine.py`)
The `generate()` function implements a **greedy algorithm** that assigns shifts while respecting:
- Unavailable dates (individual days off)
- Vacation ranges (date-based blackout periods)
- Max consecutive work days (1-3 configurable per assistant)
- Target shift counts per month (or auto-distribute evenly)
- Locked shifts (manually set entries that cannot be regenerated)

Key functions:
- `is_unavailable()`: Checks if a day is unavailable for an assistant
- `exceeds_consecutive()`: Validates consecutive day constraint
- `generate()`: Main algorithm; optional `seed` for reproducibility, `respect_locked` to preserve manual assignments

### UI Layer (`ui/`)
- **MainWindow**: Tab container with menu bar and status bar
- **TeamTab**: Manage assistants (add, remove, set colors, edit constraints via dialog)
- **PlanTab**: Calendar grid with right-click context menu (set/remove/lock shifts)
- **ConstraintsDialog**: Edit vacation ranges, unavailable dates, max consecutive days, target shifts
- **MonthSelector**: Month/year picker widget
- **ColorButton**: Color picker widget
- **CellDelegate**: Custom Qt item delegate for the schedule grid

Data flow: UI state syncs with `MonthPlan` object; manual edits trigger updates to the plan's schedule dict; generate button calls engine to recompute free slots.

### Persistence (`persistence/json_store.py`)
- `save()`: Serializes MonthPlan to JSON
- `load()`: Deserializes JSON back to MonthPlan
Plans are stored as JSON with human-readable dates and assistant references.

### Export Layer (`export/`)
- **CSVExporter**: Flat table format
- **ExcelExporter**: Uses openpyxl; preserves assistant colors as cell background colors
- **PDFExporter**: Uses reportlab; landscape orientation for readability

## Key Design Decisions

1. **Greedy Algorithm**: Simple, predictable, respects all constraints. Intentionally not optimal for fairness (could be swapped for a more sophisticated solver).
2. **Dataclasses**: All models use Python dataclasses for clarity and serialization.
3. **Seeded RNG**: The algorithm uses optional seeding for reproducible schedules (useful for testing/demo purposes).
4. **Locked Entries**: Users can manually override automatic assignments and lock them to prevent regeneration.
5. **Constraint Storage per Assistant**: Each assistant owns their own constraints; no global rules beyond per-assistant limits.

## Common Tasks

### Add a New Constraint
1. Add field to `AssistantConstraints` in `models/assistant.py`
2. Add validation logic to `scheduling/validator.py`
3. Update constraint checking in `scheduling/engine.py`
4. Add UI input field to `ConstraintsDialog` in `ui/constraints_dialog.py`
5. Update JSON serialization in `persistence/json_store.py`

### Modify the Scheduling Algorithm
Edit `scheduling/engine.py:generate()`. The current greedy approach:
- Iterates through free days
- For each day, tries to assign eligible assistants in random order
- Respects all constraints before assignment
- Supports seeding for reproducibility

### Add a New Export Format
1. Create exporter class in `export/` (implement `export(plan: MonthPlan, filepath: str)` signature)
2. Wire into menu in `main.py` (see existing CSV/Excel/PDF calls)
3. Update imports in `export/__init__.py`

### Extend the UI
The tab-based layout is in `MainWindow`. Add new tabs by:
1. Create tab class inheriting from `QWidget`
2. Instantiate in `JohannaApp.__init__()`
3. Call `self.window.tab_widget.addTab(tab, "Tab Name")`

## German Localization Notes

All UI strings, labels, and messages are in German. This is deliberate and baked into the app. If modifying UI text, maintain German throughout.

## State Management

**Single Source of Truth**: The `MonthPlan` object in `JohannaApp.plan` is the canonical schedule state. UI components read from and write to this object. When the plan is regenerated, the old schedule is replaced (unless `respect_locked=True`).

**Dirty Flag**: `MainWindow.is_modified` tracks unsaved changes. Set on plan edits, cleared on save.

## Testing Notes

There is a `test.py` stub in the root; no formal test suite is configured. For manual testing, the app initializes with dummy data (3 assistants with preset colors), allowing immediate hands-on interaction without setup.
