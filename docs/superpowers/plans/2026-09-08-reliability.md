# Wrapped reliability fixes

Goal: address the confirmed review findings without changing the personal story or publishing data.
Architecture: retain the public engine/private template split. Fix serialization and download status at their boundaries; label the existing HR estimate honestly. Run engine and private-template checks before deployment.

- [x] Add regression tests for script-boundary injection, pace rollover, failed/empty downloads and missing cached files; observe failures.
- [x] Escape HTML-sensitive JSON characters in generate.py; round pace before divmod.
- [x] Make fetch failures fatal after saving successful downloads; retry missing/empty cached FIT files.
- [x] Escape data-derived map labels in both templates and exercise the renderers with hostile labels.
- [x] Label HR zone time as an estimate in both templates and document its limitations.
- [x] Add reusable output validation, test it with invalid artifacts, and run Python/JS checks before workflow publication. Update manual-refresh documentation.
- [x] Run the full test suite and an isolated build with the personal cache/template; verify that tracked personal data did not change.

Validation: 120 Python tests, both template security checks, personal event tests, generated-page check and full offline personal-cache build passed. Workflow YAML and shell syntax checked. Remote Actions and publication were not run.
