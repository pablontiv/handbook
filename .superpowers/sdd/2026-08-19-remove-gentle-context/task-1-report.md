# Task 1 Report

## Implementation summary
- Added canonical JSON helpers with stable UTF-8 serialization and SHA-256 digesting.
- Added immutable platform/runtime models and candidate serialization.
- Added platform state-root resolution and safe-target validation.
- Added test-home guard helper.

## Files changed
- `skills/remove-gentle-context/helper/__init__.py`
- `skills/remove-gentle-context/helper/canonical.py`
- `skills/remove-gentle-context/helper/models.py`
- `skills/remove-gentle-context/helper/paths.py`
- `skills/remove-gentle-context/tests/__init__.py`
- `skills/remove-gentle-context/tests/support.py`
- `skills/remove-gentle-context/tests/test_models_paths.py`

## RED
Command:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
Output:
```text
tests.test_models_paths (unittest.loader._FailedTest.tests.test_models_paths) ... ERROR
...
ModuleNotFoundError: No module named 'helper'

FAILED (errors=1)
```

## GREEN
Focused command:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
Output:
```text
Ran 4 tests in 0.001s

OK
```

Full-suite command:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -v
```
Output:
```text
Ran 4 tests in 0.001s

OK
```

## Self-review
- Kept changes narrow to Task 1 scope.
- Used only standard library code.
- Tests use temporary directories and do not touch the real home.

## Concerns
- `models.py` currently includes placeholder exports for later tasks; they are sufficient for Task 1 but need real implementations in subsequent work.

## Fix round 1/5

### Finding 1: Plan lacked `to_unsigned_dict()` and `with_digest()`
- Changed files: `skills/remove-gentle-context/helper/models.py`, `skills/remove-gentle-context/tests/test_models_paths.py`
- Covering tests:
  - `test_plan_digest_round_trips_without_digest_field`
- RED:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- RED output (relevant):
```text
test_plan_digest_round_trips_without_digest_field ... ERROR
AttributeError: 'Plan' object has no attribute 'with_digest'
```
- GREEN:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- GREEN output: all 7 focused tests passed.

### Finding 2: Receipt missing staged fields and serialization surface
- Changed files: `skills/remove-gentle-context/helper/models.py`, `skills/remove-gentle-context/tests/test_models_paths.py`
- Covering tests:
  - `test_receipt_serializes_stage_fields`
- RED:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- RED output (relevant):
```text
AttributeError: 'Receipt' object has no attribute 'to_dict'
```
- GREEN:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- GREEN output: all 7 focused tests passed.

### Finding 3: `assert_safe_target` lacked Windows reparse-point guard
- Changed files: `skills/remove-gentle-context/helper/paths.py`, `skills/remove-gentle-context/tests/test_models_paths.py`
- Covering tests:
  - `test_safe_target_rejects_symlink`
- RED:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- RED output: initial focused run passed symlink coverage only after implementation; the guard was added before final GREEN.
- GREEN:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- GREEN output: all 7 focused tests passed.

### Finding 4: Missing explicit nonexistent-parent escape guard
- Changed files: `skills/remove-gentle-context/helper/paths.py`, `skills/remove-gentle-context/tests/test_models_paths.py`
- Covering tests:
  - `test_safe_target_rejects_nonexistent_parent_escape`
- RED:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- RED output (relevant):
```text
FileNotFoundError: [Errno 2] No such file or directory: '.../allowed/missing/../../escape.json'
```
- GREEN:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- GREEN output: all 7 focused tests passed.

### Finding 5: `from .models import *` leaked internals
- Changed files: `skills/remove-gentle-context/helper/__init__.py`
- Covering tests:
  - Import surface exercised by focused suite via `from helper import Plan, Receipt, ReceiptStatus`
- RED:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- RED output: package export surface was replaced with explicit imports before final GREEN.
- GREEN:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_models_paths.py' -v
```
- GREEN output: all 7 focused tests passed.

### Full suite
- Command:
```bash
python3 -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -v
```
- Result: `Ran 7 tests in 0.001s` / `OK`

### Self-review
- Kept changes limited to the requested contracts and path-safety fixes.
- Avoided touching deferred model schemas beyond immutable placeholders and JSON serialization hooks.
- Added explicit regression coverage for the escape case and export surface.
