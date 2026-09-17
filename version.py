"""Programmversion - die einzige Quelle der Wahrheit.

Beim Release muss der Git-Tag "v" + __version__ lauten und pyproject.toml
dieselbe Version tragen; der Build-Workflow (build-windows.yml) prueft das
bei Tag-Builds. Die Update-Pruefung (updater.py) vergleicht diese Version
mit dem neuesten GitHub-Release.
"""

__version__ = "0.3.0"

# GitHub-Repository, dessen Releases auf Updates geprueft werden
GITHUB_REPO = "ben85keilert/johanna_assistenten"
