# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-09-25

### Added

- One-way TimeTree → Google Calendar event copying.
- Normal mode for copying the next day's events.
- Optional `test_date` mode.
- Google OAuth refresh with browser reauthorization fallback.
- Dedicated-calendar safety checks.
- Refusal to modify the Google primary calendar.
- Destination calendar name verification before deletion.
- Configuration and secrets separated from source code.
- Interactive error pause, including when `config.json` is missing.
- English and Japanese documentation.
- Setup instructions for finding the TimeTree Calendar ID and `_session_id`.
- Windows Task Scheduler guidance.
- Security guidance and secret-file exclusions.

### Notes

- TimeTree access relies on an undocumented web endpoint and may break if TimeTree changes its implementation.
- This release assumes `Asia/Tokyo`.
