import json
import os
import re
import sys
import traceback
from pathlib import Path

import requests

from datetime import datetime, timedelta, timezone
from dateutil.rrule import rrulestr

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

__version__ = "1.0.0"


# ============================================================
# Configuration files
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"


def load_config():
    if not CONFIG_PATH.exists():
        print("=" * 60)
        print("Configuration error")
        print("=" * 60)
        print()
        print("config.json was not found.")
        print()
        print("Copy config.example.json to config.json,")
        print("then enter your own configuration values.")
        print()
        print(f"Checked path: {CONFIG_PATH}")
        print()
        if sys.stdin.isatty():
            input("Press Enter to exit...")
        sys.exit(1)

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    required = [
        "timetree_calendar_id",
        "timetree_session_id",
        "google_calendar_id",
        "expected_google_calendar_name",
    ]

    missing = [
        key for key in required
        if key not in config or config[key] in ("", None)
    ]

    if missing:
        raise ValueError(
            "config.json の必須項目が不足しています: "
            + ", ".join(missing)
        )

    return config


CONFIG = load_config()

TIMETREE_CALENDAR_ID = int(CONFIG["timetree_calendar_id"])
TIMETREE_SESSION_ID = str(CONFIG["timetree_session_id"])
GOOGLE_CALENDAR_ID = str(CONFIG["google_calendar_id"])
EXPECTED_GOOGLE_CALENDAR_NAME = str(
    CONFIG["expected_google_calendar_name"]
)

# null → 本番モード（翌日）
# "YYYY-MM-DD" → 指定日テスト
TEST_DATE = CONFIG.get("test_date")

# タスクスケジューラ運用では false 推奨。
PAUSE_ON_ERROR = bool(CONFIG.get("pause_on_error", True))

TIMETREE_URL = (
    f"https://timetreeapp.com/api/v1/calendar/"
    f"{TIMETREE_CALENDAR_ID}/events/sync"
)

TIMETREE_HEADERS = {
    "x-timetreea": "web/2.1.0/ja"
}

TIMETREE_COOKIES = {
    "_session_id": TIMETREE_SESSION_ID
}


# ============================================================
# Google OAuth scopes
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly"
]


# ============================================================
# Time zone
# ============================================================

JST = timezone(timedelta(hours=9))
UTC = timezone.utc


# ============================================================
# Common helpers
# ============================================================

def clean_title(title):

    if not title:
        return ""

    # Alexa読み上げ時に邪魔になる星系記号を除去
    title = re.sub(
        r"[★☆✭✮✯✰✦✧]",
        "",
        title
    )

    return title.strip()


def ms_to_datetime(ms):

    return datetime.fromtimestamp(
        ms / 1000,
        tz=JST
    )


# ============================================================
# Fetch all TimeTree chunks
# ============================================================

def get_timetree_events():

    print()
    print("========================================")
    print("TimeTree fetch")
    print("========================================")
    print()

    print(
        f"Target calendar_id: "
        f"{TIMETREE_CALENDAR_ID}"
    )

    print()

    since = 0
    all_events = []
    chunk_number = 1

    seen_since = set()


    while True:

        print(
            f"chunk {chunk_number}: "
            f"since={since}  fetching..."
        )

        response = requests.get(
            TIMETREE_URL,
            params={
                "since": since
            },
            headers=TIMETREE_HEADERS,
            cookies=TIMETREE_COOKIES,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()


        # ----------------------------------------------------
        # JSON構造の最低限チェック
        # ----------------------------------------------------

        if not isinstance(
            data,
            dict
        ):

            raise RuntimeError(
                "TimeTree APIから想定外の形式が返されました。"
            )


        if "events" not in data:

            raise RuntimeError(
                "TimeTree APIレスポンスに"
                "eventsがありません。"
            )


        if "chunk" not in data:

            raise RuntimeError(
                "TimeTree APIレスポンスに"
                "chunkがありません。"
            )


        events = data.get(
            "events",
            []
        )

        new_since = data.get(
            "since"
        )

        chunk = data.get(
            "chunk",
            False
        )


        if not isinstance(
            events,
            list
        ):

            raise RuntimeError(
                "TimeTree APIのeventsが"
                "想定外の形式です。"
            )


        print(
            f"  取得: {len(events)}件"
        )

        print(
            f"  次のsince: {new_since}"
        )

        print(
            f"  chunk: {chunk}"
        )

        print()

        all_events.extend(
            events
        )


        # ----------------------------------------------------
        # 最終chunk
        # ----------------------------------------------------

        if not chunk:
            break


        # ----------------------------------------------------
        # 無限ループ・異常レスポンス防止
        # ----------------------------------------------------

        if new_since is None:

            raise RuntimeError(
                "chunk=Trueなのにsinceがありません。"
            )


        if new_since == since:

            raise RuntimeError(
                "sinceが変化しないため、"
                "TimeTree fetchを停止しました。"
            )


        if new_since in seen_since:

            raise RuntimeError(
                "同じsinceが再度出現したため、"
                "TimeTree fetchを停止しました。"
            )


        seen_since.add(
            new_since
        )

        since = new_since
        chunk_number += 1


    print(
        "全chunkの取得が終了しました。"
    )

    print(
        f"取得総数: "
        f"{len(all_events)}件"
    )

    print()


    # ========================================================
    # 安全装置1
    #
    # 全取得結果が0件なら異常取得の可能性がある。
    # Google Calendarには一切触らず停止する。
    # ========================================================

    if len(all_events) == 0:

        raise RuntimeError(
            "TimeTreeの取得件数が0件でした。\n"
            "認証切れ・API仕様変更などによる"
            "異常取得の可能性があります。\n"
            "Google Calendarは変更しません。"
        )


    # ========================================================
    # calendar_idで再フィルタ
    # ========================================================

    filtered = []

    excluded_count = 0


    for event in all_events:

        if (
            event.get("calendar_id")
            ==
            TIMETREE_CALENDAR_ID
        ):

            filtered.append(
                event
            )

        else:

            excluded_count += 1


    print(
        f"対象カレンダー分: "
        f"{len(filtered)}件"
    )

    if excluded_count:

        print(
            f"他カレンダー除外: "
            f"{excluded_count}件"
        )


    # ========================================================
    # 安全装置2
    #
    # APIからイベントは返ったのに、
    # 対象calendar_idが1件もない場合も異常扱い。
    # ========================================================

    if len(filtered) == 0:

        raise RuntimeError(
            f"TimeTreeからイベントは取得できましたが、"
            f"calendar_id={TIMETREE_CALENDAR_ID} の"
            f"イベントが0件でした。\n"
            f"カレンダーIDまたはAPI仕様が変わった"
            f"可能性があります。\n"
            f"Google Calendarは変更しません。"
        )


    # ========================================================
    # イベントIDで重複除去
    # ========================================================

    unique = {}


    for event in filtered:

        event_id = event.get(
            "id"
        )

        if event_id:

            unique[
                event_id
            ] = event

        else:

            unique[
                f"NO_ID_{id(event)}"
            ] = event


    result = list(
        unique.values()
    )


    print(
        f"重複除去後: "
        f"{len(result)}件"
    )

    print()


    # ========================================================
    # 安全装置3
    # ========================================================

    if len(result) == 0:

        raise RuntimeError(
            "TimeTreeイベントが重複除去後0件になりました。\n"
            "想定外の状態なのでGoogle Calendarは変更しません。"
        )


    print(
        "TimeTree full fetch: OK"
    )

    print()


    return result


# ============================================================
# Target date
# ============================================================

def get_target_range():

    now = datetime.now(
        JST
    )


    # --------------------------------------------------------
    # テストモード
    # --------------------------------------------------------

    if TEST_DATE:

        try:

            target_date = datetime.strptime(
                TEST_DATE,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            raise ValueError(
                "TEST_DATE must use YYYY-MM-DD format."
            )


    # --------------------------------------------------------
    # 本番モード
    # --------------------------------------------------------

    else:

        target_date = (
            now
            + timedelta(days=1)
        ).date()


    target_start = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        0,
        0,
        0,
        tzinfo=JST
    )

    target_end = (
        target_start
        + timedelta(days=1)
    )


    print(
        f"Current time: {now}"
    )

    print(
        f"Target date: {target_date}"
    )

    print(
        f"Test mode: "
        f"{'ON' if TEST_DATE else 'OFF'}"
    )

    print()


    return (
        now,
        target_date,
        target_start,
        target_end
    )


# ============================================================
# Google cleanup start time
# ============================================================

def get_google_cleanup_start(
    now,
    target_start
):

    # --------------------------------------------------------
    # テストモード
    #
    # 指定日の0:00以降だけ掃除する。
    # 今日以降全部を消す事故を防ぐ。
    # --------------------------------------------------------

    if TEST_DATE:

        return target_start


    # --------------------------------------------------------
    # 本番モード
    #
    # 今日0:00以降を掃除する。
    # --------------------------------------------------------

    return datetime(
        now.year,
        now.month,
        now.day,
        0,
        0,
        0,
        tzinfo=JST
    )


# ============================================================
# RRULE
# ============================================================

def get_until_date(
    rrule_text
):

    match = re.search(
        r"UNTIL=(\d{8})(?:T\d{6}Z?)?",
        rrule_text
    )

    if not match:

        return None


    try:

        return datetime.strptime(
            match.group(1),
            "%Y%m%d"
        ).date()

    except ValueError:

        return None


def normalize_rrule(
    rrule_text
):

    if rrule_text.startswith(
        "RRULE:"
    ):

        rule = rrule_text.split(
            ":",
            1
        )[1]

    else:

        rule = rrule_text


    # TimeTreeの
    # UNTIL=20270401
    # のような形式をdateutil用に補正
    rule = re.sub(
        r"UNTIL=(\d{8})(?=;|$)",
        r"UNTIL=\1T235959",
        rule
    )


    return rule


# ============================================================
# EXDATE
# ============================================================

def parse_exdates(
    recurrences
):

    exdates = []


    for recurrence in recurrences:

        if not recurrence.startswith(
            "EXDATE:"
        ):

            continue


        value = recurrence.split(
            ":",
            1
        )[1]


        for item in value.split(","):

            item = item.strip()


            try:

                if item.endswith(
                    "Z"
                ):

                    dt = datetime.strptime(
                        item,
                        "%Y%m%dT%H%M%SZ"
                    )

                    dt = dt.replace(
                        tzinfo=UTC
                    )

                    dt = dt.astimezone(
                        JST
                    )

                else:

                    dt = datetime.strptime(
                        item,
                        "%Y%m%dT%H%M%S"
                    )

                    dt = dt.replace(
                        tzinfo=JST
                    )


                dt = dt.replace(
                    tzinfo=None
                )

                exdates.append(
                    dt
                )


            except ValueError:

                print(
                    f"警告: EXDATE解析失敗: "
                    f"{item}"
                )


    return exdates


def is_excluded(
    occurrence,
    exdates
):

    for exdate in exdates:

        if (
            int(
                occurrence.timestamp()
            )
            ==
            int(
                exdate.timestamp()
            )
        ):

            return True


    return False


# ============================================================
# Non-recurring events
# ============================================================

def extract_normal_event(
    event,
    target_start,
    target_end
):

    if (
        event.get("calendar_id")
        !=
        TIMETREE_CALENDAR_ID
    ):

        return []


    start_at = event.get(
        "start_at"
    )

    end_at = event.get(
        "end_at"
    )


    if start_at is None:

        return []


    start = ms_to_datetime(
        start_at
    )


    if end_at is not None:

        end = ms_to_datetime(
            end_at
        )

    else:

        end = start


    # --------------------------------------------------------
    # Target dateと重なる予定を取得
    # --------------------------------------------------------

    if (
        start < target_end
        and
        end > target_start
    ):

        return [{

            "id":
                event.get(
                    "id"
                ),

            "title":
                clean_title(
                    event.get(
                        "title",
                        ""
                    )
                ),

            "all_day":
                event.get(
                    "all_day",
                    False
                ),

            "start":
                start,

            "end":
                end,

            "recurring":
                False
        }]


    return []


# ============================================================
# Recurring events
# ============================================================

def extract_recurring_event(
    event,
    target_start,
    target_end
):

    results = []


    if (
        event.get("calendar_id")
        !=
        TIMETREE_CALENDAR_ID
    ):

        return results


    start_at = event.get(
        "start_at"
    )

    end_at = event.get(
        "end_at"
    )

    recurrences = (
        event.get(
            "recurrences"
        )
        or []
    )


    if start_at is None:

        return results


    rrules = [
        x
        for x in recurrences
        if x.startswith(
            "RRULE:"
        )
    ]


    if not rrules:

        return results


    original_start_aware = (
        ms_to_datetime(
            start_at
        )
    )


    if end_at is not None:

        original_end_aware = (
            ms_to_datetime(
                end_at
            )
        )

        duration = (
            original_end_aware
            -
            original_start_aware
        )

    else:

        duration = timedelta(0)


    # --------------------------------------------------------
    # RRULE計算用はtimezoneなしの日本時間
    # --------------------------------------------------------

    original_start = (
        original_start_aware
        .replace(
            tzinfo=None
        )
    )

    target_start_naive = (
        target_start
        .replace(
            tzinfo=None
        )
    )

    target_end_naive = (
        target_end
        .replace(
            tzinfo=None
        )
    )


    exdates = parse_exdates(
        recurrences
    )


    for rrule_text in rrules:

        until_date = get_until_date(
            rrule_text
        )


        if (
            until_date is not None
            and
            until_date
            <
            target_start.date()
        ):

            continue


        rule_text = normalize_rrule(
            rrule_text
        )


        try:

            rule = rrulestr(
                rule_text,
                dtstart=original_start
            )


        except Exception as e:

            print()
            print(
                "警告: RRULE解析失敗"
            )

            print(
                f"予定: "
                f"{clean_title(event.get('title', ''))}"
            )

            print(
                f"RRULE: "
                f"{rrule_text}"
            )

            print(
                f"理由: "
                f"{e}"
            )

            print()

            continue


        search_start = (
            target_start_naive
            -
            duration
        )


        occurrences = rule.between(
            search_start,
            target_end_naive,
            inc=True
        )


        for occurrence in occurrences:

            occurrence_end = (
                occurrence
                +
                duration
            )


            if is_excluded(
                occurrence,
                exdates
            ):

                continue


            if not (
                occurrence
                < target_end_naive
                and
                occurrence_end
                > target_start_naive
            ):

                continue


            occurrence_aware = (
                occurrence.replace(
                    tzinfo=JST
                )
            )

            occurrence_end_aware = (
                occurrence_end.replace(
                    tzinfo=JST
                )
            )


            results.append({

                "id":
                    event.get(
                        "id"
                    ),

                "title":
                    clean_title(
                        event.get(
                            "title",
                            ""
                        )
                    ),

                "all_day":
                    event.get(
                        "all_day",
                        False
                    ),

                "start":
                    occurrence_aware,

                "end":
                    occurrence_end_aware,

                "recurring":
                    True
            })


    return results


# ============================================================
# Target dateのTimeTree予定を抽出
# ============================================================

def get_target_events(
    events,
    target_start,
    target_end
):

    results = []


    for event in events:

        if (
            event.get("calendar_id")
            !=
            TIMETREE_CALENDAR_ID
        ):

            continue


        recurrences = (
            event.get(
                "recurrences"
            )
            or []
        )


        has_rrule = any(
            x.startswith(
                "RRULE:"
            )
            for x in recurrences
        )


        if has_rrule:

            extracted = (
                extract_recurring_event(
                    event,
                    target_start,
                    target_end
                )
            )

        else:

            extracted = (
                extract_normal_event(
                    event,
                    target_start,
                    target_end
                )
            )


        results.extend(
            extracted
        )


    # ========================================================
    # 重複除去
    # ========================================================

    unique = {}


    for event in results:

        key = (
            event.get(
                "id"
            ),

            int(
                event[
                    "start"
                ].timestamp()
            ),

            event.get(
                "title"
            )
        )

        unique[
            key
        ] = event


    results = list(
        unique.values()
    )


    results.sort(
        key=lambda x:
        x["start"]
    )


    return results


# ============================================================
# Display extracted TimeTree events
# ============================================================

def print_target_events(
    target_date,
    events
):

    print()
    print("========================================")
    print(
        f"{target_date} TimeTree抽出結果"
    )
    print("========================================")
    print()


    if not events:

        print(
            "No events found."
        )

        print(
            "※TimeTree全体の取得は正常なので、"
            "「対象日の予定が0件」として扱います。"
        )

        print()

        return


    for event in events:

        if event[
            "all_day"
        ]:

            text = (
                f"[終日] "
                f"{event['title']}"
            )

        else:

            text = (
                f"{event['start'].strftime('%H:%M')}"
                f" - "
                f"{event['end'].strftime('%H:%M')}"
                f"  "
                f"{event['title']}"
            )


        if event[
            "recurring"
        ]:

            text += (
                "  [繰り返し]"
            )


        print(
            text
        )


    print()

    print(
        f"Event count: "
        f"{len(events)}件"
    )

    print()


# ============================================================
# Google authentication
# ============================================================

def get_google_credentials():

    creds = None


    if TOKEN_PATH.exists():

        try:

            creds = (
                Credentials
                .from_authorized_user_file(
                    str(TOKEN_PATH),
                    SCOPES
                )
            )

        except Exception as e:

            print()
            print(
                "保存済みGoogleトークンを読み込めませんでした。"
            )
            print(
                f"理由: {e}"
            )
            print(
                "Starting Google reauthorization."
            )
            print()

            creds = None


    if not creds or not creds.valid:

        if (
            creds
            and
            creds.expired
            and
            creds.refresh_token
        ):

            print(
                "Refreshing Google token..."
            )

            try:

                creds.refresh(
                    Request()
                )

                print(
                    "Googleトークンを更新しました。"
                )

            except RefreshError as e:

                print()
                print(
                    "Googleの保存済み認証トークンが失効または無効です。"
                )
                print(
                    f"理由: {e}"
                )
                print(
                    "ブラウザでGoogleの再認証を行います。"
                )
                print()

                creds = None


        # ----------------------------------------------------
        # refreshできない場合、またはrefresh token自体がない場合は
        # InstalledAppFlowで再認証する。
        # ----------------------------------------------------

        if not creds or not creds.valid:

            if not CREDENTIALS_PATH.exists():

                raise FileNotFoundError(
                    "credentials.json was not found."
                )


            print(
                "Starting Google authentication."
            )


            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    str(CREDENTIALS_PATH),
                    SCOPES
                )
            )


            creds = flow.run_local_server(
                port=0
            )


        # ----------------------------------------------------
        # refresh成功時も再認証成功時も、最新tokenを保存する。
        # ----------------------------------------------------

        with TOKEN_PATH.open(
            "w",
            encoding="utf-8"
        ) as token:

            token.write(
                creds.to_json()
            )


    return creds



# ============================================================
# Google Calendar safety check
# ============================================================

def assert_safe_google_calendar(service):
    """
    誤ってメインカレンダー等を掃除しないための安全装置。
    config.json に指定した専用カレンダー名と実際の名前が一致し、
    かつ primary calendar でないことを確認する。
    """
    info = (
        service.calendarList()
        .get(calendarId=GOOGLE_CALENDAR_ID)
        .execute()
    )

    actual_name = info.get("summary", "")
    is_primary = bool(info.get("primary", False))

    if is_primary:
        raise RuntimeError(
            "For safety, the primary Google Calendar cannot be used.\n"
            "Create a dedicated Google Calendar for this tool."
        )

    if actual_name != EXPECTED_GOOGLE_CALENDAR_NAME:
        raise RuntimeError(
            "The Google Calendar name does not match config.json.\n"
            f"Expected: {EXPECTED_GOOGLE_CALENDAR_NAME}\n"
            f"Actual: {actual_name}\n"
            "Stopping to prevent accidental deletion."
        )

    print(
        f"Google Calendar safety check: OK "
        f"({actual_name})"
    )
    print()

# ============================================================
# Fetch Google events to delete before deleting anything
#
# この時点ではまだ削除しない。
# Google APIから正常に一覧を取得できることを確認する。
# ============================================================

def get_google_events_to_delete(
    service,
    cleanup_start
):

    print()
    print("========================================")
    print("Google Calendar cleanup preview")
    print("========================================")
    print()

    print(
        f"Cleanup starts: "
        f"{cleanup_start}"
    )

    print(
        "Cleanup ends: all future events"
    )

    print()


    page_token = None
    items_to_delete = []


    while True:

        result = (
            service.events()
            .list(
                calendarId=GOOGLE_CALENDAR_ID,

                timeMin=cleanup_start.isoformat(),

                singleEvents=True,

                pageToken=page_token
            )
            .execute()
        )


        items = result.get(
            "items",
            []
        )


        items_to_delete.extend(
            items
        )


        page_token = result.get(
            "nextPageToken"
        )


        if not page_token:

            break


    print(
        f"Events to delete: "
        f"{len(items_to_delete)}件"
    )

    print()


    for item in items_to_delete:

        print(
            f"Will delete: "
            f"{item.get('summary', '(無題)')}"
        )


    if items_to_delete:

        print()


    return items_to_delete


# ============================================================
# Delete Google events
# ============================================================

def delete_google_events(
    service,
    items_to_delete
):

    print()
    print("========================================")
    print("Google Calendar cleanup")
    print("========================================")
    print()


    delete_count = 0


    for item in items_to_delete:

        event_id = item.get(
            "id"
        )

        title = item.get(
            "summary",
            "(無題)"
        )


        if not event_id:

            raise RuntimeError(
                "削除対象Googleイベントに"
                "event IDがありません。"
            )


        print(
            f"Delete: "
            f"{title}"
        )


        (
            service.events()
            .delete(
                calendarId=GOOGLE_CALENDAR_ID,
                eventId=event_id
            )
            .execute()
        )


        delete_count += 1


    if delete_count == 0:

        print(
            "No events to delete."
        )


    print()

    print(
        f"Deleted: "
        f"{delete_count}件"
    )

    print()


# ============================================================
# Insert one Google event
# ============================================================

def insert_google_event(
    service,
    event
):

    title = event[
        "title"
    ]

    all_day = event[
        "all_day"
    ]

    start = event[
        "start"
    ]

    end = event[
        "end"
    ]


    # --------------------------------------------------------
    # 終日予定
    # --------------------------------------------------------

    if all_day:

        start_date = (
            start
            .astimezone(
                JST
            )
            .date()
        )


        # Google Calendarの終日予定では
        # end.dateは排他的
        end_date = (
            start_date
            +
            timedelta(days=1)
        )


        body = {

            "summary":
                title,

            "start": {
                "date":
                    start_date.isoformat()
            },

            "end": {
                "date":
                    end_date.isoformat()
            }
        }


    # --------------------------------------------------------
    # 時刻指定予定
    # --------------------------------------------------------

    else:

        body = {

            "summary":
                title,

            "start": {
                "dateTime":
                    start.isoformat(),

                "timeZone":
                    "Asia/Tokyo"
            },

            "end": {
                "dateTime":
                    end.isoformat(),

                "timeZone":
                    "Asia/Tokyo"
            }
        }


    created = (
        service.events()
        .insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=body
        )
        .execute()
    )


    return created


# ============================================================
# Insert all Google events
# ============================================================

def insert_google_events(
    service,
    events
):

    print()
    print("========================================")
    print("Google Calendar event insertion")
    print("========================================")
    print()


    count = 0


    if not events:

        print(
            "登録するNo events found."
        )

        print()

        print(
            "Alexa読み上げカレンダーは"
            "空の状態になります。"
        )

        print()

        return 0


    for event in events:

        insert_google_event(
            service,
            event
        )


        if event[
            "all_day"
        ]:

            print(
                f"Insert: "
                f"[終日] "
                f"{event['title']}"
            )


        else:

            print(
                f"Insert: "
                f"{event['start'].strftime('%H:%M')}"
                f" - "
                f"{event['end'].strftime('%H:%M')}"
                f"  "
                f"{event['title']}"
            )


        count += 1


    print()

    print(
        f"Inserted: "
        f"{count}件"
    )

    print()


    return count


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    try:

        print()
        print("========================================")
        print("TimeTree → Google Calendar")
        print("========================================")
        print()


        # ====================================================
        # 1. 対象日決定
        # ====================================================

        (
            now,
            target_date,
            target_start,
            target_end
        ) = get_target_range()


        # ====================================================
        # 2. TimeTree全取得
        #
        # ここで異常ならGoogleには一切触らない
        # ====================================================

        timetree_events = (
            get_timetree_events()
        )


        # ====================================================
        # 3. 翌日 / テスト対象日の予定を抽出
        # ====================================================

        target_events = (
            get_target_events(
                timetree_events,
                target_start,
                target_end
            )
        )


        # ====================================================
        # 4. 抽出結果を確認
        #
        # 0件でも、TimeTree全体取得が正常なら正常扱い
        # ====================================================

        print_target_events(
            target_date,
            target_events
        )


        print(
            "========================================"
        )

        print(
            "TimeTree fetch・解析 正常"
        )

        print(
            "Google Calendar will now be updated."
        )

        print(
            "========================================"
        )

        print()


        # ====================================================
        # 5. Google認証
        # ====================================================

        print(
            "Connecting to Google Calendar..."
        )

        creds = (
            get_google_credentials()
        )

        service = build(
            "calendar",
            "v3",
            credentials=creds
        )


        # ====================================================
        # 5.5 Google Calendar安全確認
        # ====================================================

        assert_safe_google_calendar(
            service
        )


        # ====================================================
        # 6. Google掃除開始日時
        #
        # 本番:
        #   今日0:00以降
        #
        # TEST_DATE:
        #   指定日0:00以降
        # ====================================================

        cleanup_start = (
            get_google_cleanup_start(
                now,
                target_start
            )
        )


        # ====================================================
        # 7. Google削除対象を取得
        #
        # まだ削除しない。
        # Google APIの読み取りが正常なことを確認。
        # ====================================================

        items_to_delete = (
            get_google_events_to_delete(
                service,
                cleanup_start
            )
        )


        # ====================================================
        # 8. Google既存予定を削除
        # ====================================================

        delete_google_events(
            service,
            items_to_delete
        )


        # ====================================================
        # 9. TimeTree対象日予定をGoogleへ登録
        # ====================================================

        inserted_count = (
            insert_google_events(
                service,
                target_events
            )
        )


        # ====================================================
        # 10. 正常終了
        # ====================================================

        print()
        print("========================================")
        print("Completed")
        print("========================================")
        print()

        print(
            f"{target_date} のTimeTree予定を"
        )

        print(
            "Google「Alexa読み上げ」に反映しました。"
        )

        print()

        print(
            f"Inserted: "
            f"{inserted_count}件"
        )

        print()

        print(
            "Finished successfully."
        )

        print()


    except Exception:

        # ====================================================
        # エラー時
        #
        # 正常時は自動終了。
        # エラー時だけ永久待機。
        # ====================================================

        print()
        print("========================================")
        print("An error occurred")
        print("========================================")
        print()

        traceback.print_exc()

        print()
        print("========================================")
        print(
            "The process ended with an error."
        )
        print(
            "Review the error details above."
        )
        print("========================================")
        print()

        if PAUSE_ON_ERROR and sys.stdin.isatty():
            input(
                "Press Enter to exit..."
            )

        sys.exit(1)
