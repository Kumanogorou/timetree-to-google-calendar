# v1.0.0

First public release of **TimeTree to Google Calendar**.

A small Python bridge that copies TimeTree events to a dedicated Google Calendar, intended for workflows such as:

`TimeTree → Google Calendar → Alexa`

## Highlights

- One-way copying with TimeTree as the source of truth
- Dedicated Google Calendar safety checks
- Google OAuth refresh and reauthorization fallback
- Secrets kept out of the source code
- Windows Task Scheduler friendly
- English and Japanese documentation

## Important

This project uses an undocumented internal TimeTree Web endpoint. It is not an official TimeTree integration and may require maintenance if TimeTree changes its web implementation.

Always use a dedicated destination Google Calendar. Do not point the script at your primary calendar.
