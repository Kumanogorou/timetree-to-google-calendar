# TimeTree → Google Calendar

English: [README.md](README.md)

TimeTree の予定を取得し、指定した Google Calendar にコピーする個人向け Python スクリプトです。

主な用途は、**TimeTree → Google Calendar → Alexa** のように、Google Calendar を中継用カレンダーとして使うことです。

> [!WARNING]
> このツールは TimeTree の公式公開 API を使用していません。TimeTree Web 版が利用している内部 API に依存するため、TimeTree 側の仕様変更で突然動かなくなる可能性があります。TimeTree 公式のツールではありません。

## 重要な安全上の注意

このスクリプトは、設定した Google Calendar の予定を削除してから TimeTree の予定を登録します。

**普段使っているメインカレンダーを絶対に指定しないでください。**  
必ず、このツール専用の Google Calendar（例: `Alexa読み上げ`）を新規作成してください。

公開版には次の安全装置を追加しています。

- TimeTree の取得・解析が正常終了するまで Google Calendar を変更しない
- Google Calendar の削除対象を先に全件取得してから削除を開始
- Google の primary calendar なら処理を拒否
- Google Calendar の実際の名前が `expected_google_calendar_name` と一致しなければ処理を拒否
- 認証情報・セッション情報をソースコードから分離
- エラー時は既定で Enter キー待ちにして、エラー画面が閉じない
- `config.json` 自体が存在しない場合も、設定エラーを表示して Enter キー待ちにする

## 動作概要

通常モードでは次の処理を行います。

1. TimeTree からイベントを取得
2. 翌日の予定を抽出
3. TimeTree 側が正常に取得できたことを確認
4. Google Calendar に接続
5. 専用カレンダーであることを安全確認
6. Google Calendar の「今日 0:00 以降」の予定を取得
7. 取得できた削除対象を削除
8. 翌日の TimeTree 予定を Google Calendar に登録

`test_date` を指定すると、指定日の予定だけをコピーするテストモードになります。

## 必要なもの

- Python 3
- TimeTree アカウント
- Google アカウント
- Google Cloud の OAuth Desktop Client
- Google Calendar API
- コピー先として使用する**専用 Google Calendar**

## インストール

このフォルダで以下を実行します。

```bash
python -m pip install -r requirements.txt
```

## 1. Google Calendar を作る

Google Calendar に、このツール専用のカレンダーを作ります。

例:

```text
Alexa読み上げ
```

このカレンダーの Calendar ID を控えます。

**メインカレンダーは使用しないでください。**

## 2. Google Cloud を設定する

Google Cloud でプロジェクトを作成し、Google Calendar API を有効にします。

OAuth クライアントは **Desktop app** として作成し、ダウンロードした JSON をこのフォルダに

```text
credentials.json
```

という名前で保存します。

長期間の無人運用を行う場合、OAuth consent screen が Testing のままだと refresh token の運用で問題になる場合があります。必要に応じて Google Auth Platform の公開ステータスを確認してください。

`credentials.json` は秘密情報です。GitHub 等へ公開しないでください。

## 3. TimeTree の Calendar ID と `_session_id` を取得する

このスクリプトは TimeTree Web 版が使用している内部 API を利用します。

必要なのは次の2つです。

- `timetree_calendar_id` : コピー元 TimeTree カレンダーの ID
- `timetree_session_id` : ログイン中ブラウザの `_session_id` cookie

以下は **Google Chrome / Microsoft Edge など Chromium 系ブラウザ**を想定した手順です。ブラウザのバージョンによってメニュー名や表示位置が多少変わることがあります。

> [!CAUTION]
> `_session_id` は認証済みセッションに関係する秘密情報です。パスワードと同様に扱ってください。GitHub、ブログ、Issue、スクリーンショット、チャット等へ公開しないでください。

### 3-1. TimeTree Web にログインする

PC のブラウザで TimeTree Web を開き、通常どおりログインします。

目的のカレンダーを開き、予定が表示されていることを確認してください。

### 3-2. 開発者ツールを開く

TimeTree を開いた状態で、次のいずれかで開発者ツールを開きます。

```text
F12
```

または

```text
Ctrl + Shift + I
```

### 3-3. Network を開く

開発者ツール上部の **Network**（ネットワーク）タブを選択します。

Network を開いた状態で TimeTree のページを再読み込みします。

```text
Ctrl + R
```

通信が多数表示されます。

### 3-4. `events/sync` を探す

Network のフィルター欄に、

```text
events/sync
```

と入力します。

TimeTree のイベント同期通信が表示されたら、その行をクリックします。

Request URL は概ね次の形です。

```text
https://timetreeapp.com/api/v1/calendar/12345678/events/sync?...
```

この例の

```text
12345678
```

に相当する数字が **TimeTree Calendar ID** です。

つまり、

```text
/api/v1/calendar/＜この数字＞/events/sync
```

の `＜この数字＞` を `config.json` の

```json
"timetree_calendar_id": 12345678
```

へ設定します。

複数の TimeTree カレンダーを利用している場合は、**コピーしたいカレンダーを表示した状態で取得した ID であることを確認してください。**

### 3-5. `_session_id` を取得する

同じ `events/sync` 通信を選択した状態で、**Headers**（ヘッダー）を開きます。

Request Headers の中に `Cookie` があれば、その内容から

```text
_session_id=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

を探します。

必要なのは `=` より後ろの値だけです。

例えばブラウザ上で、

```text
_session_id=ABCDEF1234567890; other_cookie=...
```

となっていた場合、`config.json` には、

```json
"timetree_session_id": "ABCDEF1234567890"
```

と設定します。

`Cookie` が Headers に表示されない場合は、次の方法でも確認できます。

1. 開発者ツールの **Application** タブを開く
2. 左側の **Storage → Cookies** を展開
3. `https://timetreeapp.com` を選択
4. Cookie 一覧から `_session_id` を探す
5. **Value** の内容をコピーする

Edge 等では `Application` の名称や配置が若干異なる場合があります。

### 3-6. 取得した値を `config.json` に入れる

最終的には例えば次のようになります。

```json
{
  "timetree_calendar_id": 12345678,
  "timetree_session_id": "YOUR_SESSION_ID_HERE",
  "google_calendar_id": "xxxxxxxxxxxxxxxx@group.calendar.google.com",
  "expected_google_calendar_name": "Alexa読み上げ",
  "test_date": null,
  "pause_on_error": true
}
```

### 3-7. 取得できない場合

`events/sync` が見つからない場合は、次を順に試してください。

- Network を開いてから TimeTree を再読み込みする
- Network のフィルターを一度消して通信が記録されているか確認する
- 目的のカレンダーを別のカレンダーへ切り替えてから戻す
- Network の **Fetch/XHR** を選択して絞り込む
- TimeTree からログアウトしていないか確認する

TimeTree 側の Web 実装が変更された場合、URL や取得方法そのものが変わる可能性があります。

### 3-8. セッションが失効した場合

TimeTree の `_session_id` は永久に有効とは限りません。

スクリプトが TimeTree へアクセスできなくなった場合は、ブラウザで TimeTree に正常にログインできることを確認し、上記手順で現在の `_session_id` を取得して `config.json` を更新してください。

> [!IMPORTANT]
> `config.json` は `.gitignore` の対象です。実際の `_session_id` を `config.example.json` や Python ソースへ直接書かないでください。

### 3-9. 開発者ツールが分からなければ ChatGPT に聞く

ブラウザの開発者ツールに慣れていない場合は、無理にこの README だけで解決しなくても構いません。ChatGPT 等に、次のように聞くと画面を見ながら案内してもらいやすいです。

```text
TimeTree Web版から、自分のカレンダーのCalendar IDを
Chromeの開発者ツールで確認する方法を教えて。
```

```text
TimeTree Web版にログイン済みです。
Chromeの開発者ツールからCookieの _session_id が
どこにあるか、クリックする場所を順番に教えて。
実際の _session_id の値は送らない前提でお願いします。
```

まとめて聞くなら、

```text
TimeTree Web版の開発者ツールを使って、
Calendar IDと _session_id を自分で確認し、
Pythonスクリプトのconfig.jsonに設定したいです。
秘密情報そのものは送らずに済む手順を教えて。
```

でも十分です。

スクリーンショットを使って質問する場合も、`_session_id`、Cookie、OAuth の client secret、`token.json` の内容などの秘密情報が写っていないことを確認してから送ってください。


## 4. config.json を作る

`config.example.json` をコピーして `config.json` に名前を変更します。

```json
{
  "timetree_calendar_id": 12345678,
  "timetree_session_id": "PASTE_YOUR_TIMETREE_SESSION_ID_HERE",
  "google_calendar_id": "xxxxxxxxxxxxxxxx@group.calendar.google.com",
  "expected_google_calendar_name": "Alexa読み上げ",
  "test_date": null,
  "pause_on_error": true
}
```

### 各項目

`timeTree_calendar_id` ではなく、正しいキー名は `timetree_calendar_id` です。

- `timetree_calendar_id`: TimeTree の Calendar ID
- `timetree_session_id`: TimeTree の `_session_id`
- `google_calendar_id`: コピー先の専用 Google Calendar ID
- `expected_google_calendar_name`: コピー先カレンダーの表示名。誤削除防止に使用
- `test_date`: 通常は `null`。テスト時のみ `"2026-09-25"` のように指定
- `pause_on_error`: `true` にすると、エラー時に Enter キー待ちになり画面が閉じません（公開版の既定値）

## 5. 初回実行

```bash
python timetree_to_google.py
```

初回はブラウザで Google OAuth 認証が行われます。

成功すると `token.json` が生成されます。以後は通常、refresh token を使って自動更新されます。

保存済み refresh token が失効・無効になった場合は `RefreshError` を捕捉し、ブラウザ OAuth にフォールバックします。その場合だけ人間の再認証が必要になることがあります。

## 6. テスト

最初から本番カレンダーを大量に触らせず、専用のテスト用カレンダーを作ることを推奨します。

`config.json` の

```json
"test_date": "2026-09-25"
```

のように日付を指定すると、その日の TimeTree 予定を対象にできます。

確認後は必ず

```json
"test_date": null
```

へ戻してください。

## Windows タスクスケジューラ

無人運用では、タスクスケジューラから例えば次のように実行できます。

**プログラム/スクリプト**

```text
C:\Path\To\Python\python.exe
```

**引数の追加**

```text
"C:\Path\To\timetree-to-google\timetree_to_google.py"
```

この公開版は設定・OAuthファイルをスクリプト自身のフォルダから読むため、タスクスケジューラの「開始 (オプション)」に依存しません。

## ファイル構成

```text
timetree-to-google/
├── timetree_to_google.py
├── config.example.json
├── requirements.txt
├── README.md
├── .gitignore
├── config.json          # 自分で作る / 公開禁止
├── credentials.json     # Googleから取得 / 公開禁止
└── token.json           # 初回認証後に生成 / 公開禁止
```

## GitHub に公開する前の確認

次のファイルが commit 対象に入っていないことを必ず確認してください。

```text
config.json
credentials.json
token.json
```

さらに、ソースや README に以下が残っていないか検索してください。

- 実際の `_session_id`
- 実際の TimeTree Calendar ID
- 実際の Google Calendar ID
- OAuth client secret
- 自分のメールアドレス

## 制限事項

- TimeTree の非公開・内部 API に依存しています。
- TimeTree の仕様変更で動作しなくなる可能性があります。
- TimeTree セッションが失効した場合は `_session_id` の更新が必要になる可能性があります。
- Google OAuth の refresh token も、ユーザーによるアクセス取り消し等で失効することがあります。
- タイムゾーンは現在 `Asia/Tokyo` / JST 前提です。
- 本ツールは TimeTree、Google、Amazon/Alexa の公式ツールではありません。

## 設計上の考え方

このツールでは「完全同期」よりも安全性を優先しています。

TimeTree を予定の正本とし、Google Calendar は Alexa 等から読むための一時的な中継先として扱います。そのため Google 側で予定を編集しても TimeTree へは戻りません。

また、TimeTree の取得に異常がある状態では Google Calendar を変更しないようにしています。

## 免責

利用は自己責任でお願いします。特に Google Calendar の削除処理を含むため、必ず専用カレンダーで十分にテストしてから自動実行してください。

## バージョン

現在の公開版: **v1.0.0**

変更内容は [CHANGELOG.md](CHANGELOG.md) を参照してください。

## ライセンス

[MIT License](LICENSE) で公開します。
