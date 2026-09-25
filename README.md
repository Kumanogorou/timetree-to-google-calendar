# TimeTree → Google Calendar

A personal Python tool that reads events from TimeTree and copies them to a dedicated Google Calendar.

A typical use case is:

```text
TimeTree → Google Calendar → Alexa
```

TimeTree remains the source of truth. Google Calendar is used only as an intermediary calendar that Alexa or another service can read.

> [!WARNING]
> This project does **not** use an official public TimeTree API. It depends on an internal endpoint used by the TimeTree web application. TimeTree may change that endpoint or its data format at any time and break this tool. This project is not affiliated with or endorsed by TimeTree, Google, or Amazon.

Japanese documentation: [README_JP.md](README_JP.md)

## Important safety warning

This script deletes events from the configured destination Google Calendar before copying TimeTree events into it.

**Never configure your primary or everyday Google Calendar as the destination.**

Create a dedicated calendar for this tool, for example:

```text
Alexa
```

The public version includes several safeguards:

- Google Calendar is not modified until TimeTree retrieval and parsing complete successfully.
- Events to be deleted are fetched successfully before deletion starts.
- The script refuses to operate on the Google primary calendar.
- The actual destination calendar name must exactly match `expected_google_calendar_name`.
- Session IDs and OAuth credentials are kept outside the Python source.
- Errors remain visible in an interactive console until Enter is pressed.
- A missing `config.json` also displays an error and waits for Enter.

## How it works

In normal mode the script:

1. Retrieves TimeTree events.
2. Extracts events for tomorrow.
3. Confirms that TimeTree retrieval and parsing succeeded.
4. Authenticates with Google Calendar.
5. Verifies that the configured calendar is the intended dedicated calendar.
6. Lists events from today 00:00 onward in that calendar.
7. Deletes those destination events.
8. Copies tomorrow's TimeTree events to Google Calendar.

If `test_date` is specified, the script runs against that date instead.

## Requirements

- Python 3
- A TimeTree account
- A Google account
- A Google Cloud OAuth Desktop Client
- Google Calendar API enabled
- A **dedicated Google Calendar** used only by this tool

## Installation

Run:

```bash
python -m pip install -r requirements.txt
```

## 1. Create a dedicated Google Calendar

Create a new Google Calendar specifically for this script.

Example:

```text
Alexa
```

Copy its Calendar ID. Do **not** use your primary calendar.

## 2. Configure Google Cloud

Create a Google Cloud project and enable the Google Calendar API.

Create an OAuth client of type **Desktop app**. Download the client JSON and save it in this project directory as:

```text
credentials.json
```

If you intend to run the script unattended for a long period, review the publishing status of the OAuth consent configuration in Google Auth Platform. OAuth behavior and verification requirements may change, so refer to Google's current documentation when setting up a new project.

`credentials.json` contains sensitive OAuth information. Never commit or publish it.

## 3. Obtain the TimeTree Calendar ID and `_session_id`

This tool uses the internal API used by TimeTree Web.

You need:

- `timetree_calendar_id`: the source TimeTree calendar ID
- `timetree_session_id`: the `_session_id` cookie from your logged-in TimeTree Web session

The following steps assume Chrome, Edge, or another Chromium-based browser. Browser UI labels may vary.

> [!CAUTION]
> `_session_id` is authentication-related secret information. Treat it like a password. Never post the actual value on GitHub, a blog, an issue tracker, screenshots, chat, or other public locations.

### 3.1 Log in to TimeTree Web

Open TimeTree Web on a desktop browser, log in normally, and open the calendar you want to copy.

### 3.2 Open Developer Tools

Press:

```text
F12
```

or:

```text
Ctrl + Shift + I
```

### 3.3 Open Network

Select the **Network** tab and reload TimeTree:

```text
Ctrl + R
```

### 3.4 Find `events/sync`

Enter:

```text
events/sync
```

in the Network filter.

Select the matching request. Its Request URL should look roughly like:

```text
https://timetreeapp.com/api/v1/calendar/12345678/events/sync?...
```

The number between `calendar/` and `/events/` is the **TimeTree Calendar ID**:

```text
/api/v1/calendar/12345678/events/sync
                 ^^^^^^^^
                 Calendar ID
```

Put that number into `config.json`:

```json
"timetree_calendar_id": 12345678
```

If you use multiple TimeTree calendars, make sure the ID belongs to the calendar you actually want to copy.

### 3.5 Find `_session_id`

With the same `events/sync` request selected, open **Headers** and inspect the request cookies.

Look for:

```text
_session_id=xxxxxxxxxxxxxxxx
```

Only the value after `=` is required.

Alternatively:

1. Open Developer Tools → **Application**.
2. Expand **Storage → Cookies**.
3. Select `https://timetreeapp.com`.
4. Find `_session_id`.
5. Copy its **Value**.

Put it into `config.json`:

```json
"timetree_session_id": "YOUR_SESSION_ID_HERE"
```

### 3.6 If you cannot find the values

Try:

- Open Network before reloading TimeTree.
- Remove any Network filters and confirm requests are being recorded.
- Switch to another TimeTree calendar and back.
- Filter Network to **Fetch/XHR**.
- Confirm that you are still logged in.

Because this is an undocumented TimeTree interface, the endpoint or cookie behavior may change.

### 3.7 If the TimeTree session expires

`_session_id` is not guaranteed to remain valid forever.

If TimeTree authentication starts failing, log in to TimeTree Web again, obtain the current `_session_id`, and update `config.json`.

### 3.8 Ask ChatGPT for guidance

If you are unfamiliar with browser Developer Tools, you can ask ChatGPT to guide you without sending the secret itself.

For example:

```text
How can I find my TimeTree Calendar ID using Chrome Developer Tools
on the TimeTree Web app?
```

```text
I am already logged in to TimeTree Web.
Show me step by step where to find the _session_id cookie in Chrome
Developer Tools. I will not send you the actual cookie value.
```

Or:

```text
I need to find the Calendar ID and _session_id from TimeTree Web
and put them into a Python script's config.json.
Please guide me through Developer Tools without asking me to send
any secret values.
```

If you use screenshots when asking for help, redact or hide `_session_id`, other cookies, OAuth client secrets, and the contents of `token.json`.

## 4. Create `config.json`

Copy:

```text
config.example.json
```

to:

```text
config.json
```

Then enter your own values:

```json
{
  "timetree_calendar_id": 12345678,
  "timetree_session_id": "YOUR_SESSION_ID_HERE",
  "google_calendar_id": "xxxxxxxxxxxxxxxx@group.calendar.google.com",
  "expected_google_calendar_name": "Alexa",
  "test_date": null,
  "pause_on_error": true
}
```

Fields:

- `timetree_calendar_id` — source TimeTree Calendar ID
- `timetree_session_id` — TimeTree `_session_id`
- `google_calendar_id` — destination dedicated Google Calendar ID
- `expected_google_calendar_name` — expected display name of that calendar; used as a deletion safeguard
- `test_date` — normally `null`; use `"YYYY-MM-DD"` for testing
- `pause_on_error` — when `true`, an interactive console waits for Enter after an error

## 5. First run

Run:

```bash
python timetree_to_google.py
```

On the first run, Google OAuth opens in your browser.

After successful authorization, `token.json` is created. Normally the stored refresh token is then used for subsequent authentication.

If refreshing the Google token fails with `RefreshError`, the script falls back to browser OAuth. Human interaction may therefore still be required if the saved authorization becomes invalid or is revoked.

## 6. Test before automating

Using a separate test calendar first is strongly recommended.

To test a specific date:

```json
"test_date": "2026-09-25"
```

After testing, restore:

```json
"test_date": null
```

## Windows Task Scheduler

A typical Task Scheduler configuration is:

**Program/script**

```text
C:\Path\To\Python\python.exe
```

**Add arguments**

```text
"C:\Path\To\timetree-to-google\timetree_to_google.py"
```

The script resolves `config.json`, `credentials.json`, and `token.json` relative to its own directory, so it does not depend on Task Scheduler's working directory.

## Files

```text
timetree-to-google/
├── timetree_to_google.py
├── config.example.json
├── requirements.txt
├── README.md
├── README_JP.md
├── SECURITY.md
├── .gitignore
├── config.json          # create locally / DO NOT PUBLISH
├── credentials.json     # downloaded from Google / DO NOT PUBLISH
└── token.json           # generated after OAuth / DO NOT PUBLISH
```

## Before publishing to GitHub

Verify that these files are not staged or committed:

```text
config.json
credentials.json
token.json
```

Also search the repository for:

- your real `_session_id`
- your real TimeTree Calendar ID
- your real Google Calendar ID
- OAuth client secrets
- personal email addresses

## Limitations

- Depends on an undocumented TimeTree Web endpoint.
- TimeTree changes may break the script without warning.
- An expired TimeTree session may require a new `_session_id`.
- Google OAuth authorization can be revoked or become invalid.
- The current implementation assumes Japan Standard Time / `Asia/Tokyo`.
- This is one-way copying, not bidirectional synchronization.
- The tool is not affiliated with TimeTree, Google, or Amazon/Alexa.

## Design philosophy

TimeTree is treated as the source of truth. Google Calendar is only a temporary intermediary for services such as Alexa.

Safety is intentionally prioritized over aggressive synchronization. If TimeTree retrieval or parsing fails, the script should stop before modifying Google Calendar.

## Disclaimer

Use at your own risk. The script performs deletion operations on the configured Google Calendar. Always use a dedicated calendar and test carefully before scheduling unattended runs.

## Version

Current public release: **v1.0.0**

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## License

Released under the [MIT License](LICENSE).
