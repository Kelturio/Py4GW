# ItemCompare.py Overview

## Purpose and Context
`ItemCompare.py` is a legacy ImGui script that renders several debug-style windows for inspecting Guild Wars item data inside the Py4GW environment. It relies heavily on `Py4GWCoreLib` for interacting with the client (item inventories, modifiers, enumerations) and uses global state and immediate-mode rendering helpers to show:

* A side-by-side comparison of two inventory items.
* A description view for the currently selected main-hand item.
* A description view for off-hand items.

The module appears to have been prototyped as a "modifier decoder" as well, although that feature is currently incomplete.

## Core Data Structures
The file defines a small `ModifierInfo` class that captures metadata about an item modifier (`identifier`, friendly `name`, display labels for `arg`, `arg1`, `arg2`, and optional evaluator callables). Instances of this class are stored in a global dictionary named `modifiers` via the helper `add_modifier()`; lookups use `find_modifier(identifier)` to retrieve metadata by the in-game identifier.【F:Legacy code and tests/ItemCompare.py†L14-L45】

Supporting helper functions (`Value`, `GetAttributeName`, `GetDamageType`, `GetAilment`, `GetReducedAilment`, `GetInscription`) translate raw IDs returned by the game API into friendly names by consulting enums defined in `Py4GWCoreLib`. They silently fall back to returning the raw identifier if an enum lookup fails, preventing crashes when new IDs are encountered.【F:Legacy code and tests/ItemCompare.py†L47-L80】

A large block of `add_modifier(...)` calls hard-codes known modifiers, inscriptions, and runes. Each entry specifies:

* Which parts of the modifier payload should be shown (`arg`, `arg1`, `arg2`).
* Optional evaluator lambdas to map raw numbers to user-facing strings.
* A `representation` lambda that formats the modifier as a sentence for display.【F:Legacy code and tests/ItemCompare.py†L82-L1000】

These definitions drive every user-facing description in the UI; unknown IDs fall back to raw numeric output so that the operator can still spot discrepancies.

## UI Windows
All windows share the same `window_module` configuration (`"Item Compare"` title, 300×300 default). Each function reuses this module, which means the first window to render controls the `first_run` flag and subsequent windows skip their own size/position initialization.【F:Legacy code and tests/ItemCompare.py†L11-L31】【F:Legacy code and tests/ItemCompare.py†L1038-L1391】

### Item description windows
`ShowItemdescription()` and `ShowOffhandItemdescription()` fetch the first item from the aggregated inventory bags and print its core stats alongside formatted modifier lines. `ShowItemdescription()` has special handling for weapon damage: it looks up the damage type (ID `9400`), damage range (`42920`), and attribute requirement (`10136`) and combines their text into a single headline before listing the remaining modifiers. Both functions skip modifiers whose names start with `"Unknown"`, preventing placeholder definitions from cluttering the output.【F:Legacy code and tests/ItemCompare.py†L1001-L1199】

### Comparison window
`ShowItemComparisonWindow()` pulls the first two items from the same bag set and renders a table comparing common item metadata (type, model, slot, agent IDs) and an expandable section for modifiers. For each modifier identifier observed on either item, it:

1. Collects the raw argument tuple from each item.
2. Looks up metadata via `find_modifier` and runs the evaluator functions to make values human-readable.
3. Builds a table row showing either the formatted sentences (for known modifiers) or the raw arguments (for unknown modifiers).
4. Colors the output cyan when a modifier definition exists, green when the raw payloads match, and red otherwise.【F:Legacy code and tests/ItemCompare.py†L1233-L1373】

The window assumes at least two items exist in the combined bag list and does not handle empty slots gracefully—`input_item1 = item_array[0]` will raise an index error if the bag list is empty.【F:Legacy code and tests/ItemCompare.py†L1249-L1262】

## Error Handling and Lifecycle
Each window function wraps its UI logic in a `try/except` block that logs errors to the Py4GW console with the module name. The `main()` entry point simply calls all three window functions every frame and logs detailed stack traces if something goes wrong, ensuring that UI exceptions do not silently fail.【F:Legacy code and tests/ItemCompare.py†L1375-L1414】

## Notable Gaps and Quirks
* `ShowModifierDecoderWindow()` references an undefined helper `decode_modifier()`, so the feature cannot work without additional implementation. The surrounding triple-quoted string hints that the block might have been commented out previously.【F:Legacy code and tests/ItemCompare.py†L1201-L1229】
* The `window_module` global is reused for all windows. Because `first_run` is flipped to `False` after the first window renders, later windows may not get their intended initial size/position setup, and they also share title/flags even though the UI labels differ.
* Inventory accessors always read the first (and for comparisons, second) element of the aggregated bag array without validating length, so empty inventories or single-item scenarios may throw `IndexError`.【F:Legacy code and tests/ItemCompare.py†L1249-L1262】
* Several module-level symbols (`json_file_path`, the `Enum` import) are unused, suggesting unfinished plans for loading modifier metadata from disk.

Overall, `ItemCompare.py` is a data-heavy diagnostic tool that manually encodes Guild Wars item modifier knowledge to make debugging easier inside the Py4GW framework. The reliance on hard-coded tables and shared globals reflects its legacy/prototype status, but the rendering logic demonstrates how modifier metadata is transformed into human-readable descriptions.
