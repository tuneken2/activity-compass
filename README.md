# Activity Compass

Codex / Claude Codeの会話で決まった活動情報を、合言葉ひとつでローカル管理するWindows向けMVPです。

正式コマンド：

> ここまでの活動情報を管理アプリに反映して

短縮コマンド：

> 活動管理に反映して

上記の明示的な依頼があったときだけSkillが会話から変更イベントを抽出し、MCP経由でローカルアプリへ送ります。「同期」「保存」などの一般語だけでは発動しません。

## 必要環境

- Windows 10または11
- Python 3.10以上
- CodexまたはClaude Code（会話連携を使う場合）
- PowerShell 5.1以上

本アプリはローカル専用です。APIキーは使用せず、活動データをクラウドへ送信しません。ただしCodex / Claude Codeとの通常の会話には、それぞれのサービスの通信・データ取扱条件が適用されます。

## 実装済み

- タスク、予定、アイデア、待ち、決定、プロジェクトの保存
- 今日、次、待ち、いつか、確認待ち、更新履歴、すべての画面
- 起動時に開き、プロジェクトごとの所属タスクをクリックで展開・折りたたみできるプロジェクト一覧
- プロジェクト一覧の優先度（高・中・低）と、同一優先度内のプロジェクト序列による並べ替え
- プロジェクトごとのカテゴリー設定・カテゴリー色と、プロジェクト別イメージカラーによる一覧の色分け
- 一覧では優先度を「高・中・低」で表示（手動入力・APIでは3・2・1）し、所属プロジェクト・期限・工数からタスク優先度を自動算出
- 自然文会話からの一括作成・更新・完了・取消・延期・補足
- 新規追加と安全な補足の自動反映、タイトル一致による重複抑止
- 曖昧な完了・取消・延期・期限変更の確認待ち
- 全文検索、詳細編集、状態変更、手動クイック追加
- 期限・予定日が来た項目の「今日」への自動浮上
- アプリ起動中の非同期リマインダー
- SQLiteの日次バックアップ（14世代）とJSON書き出し
- 同期バッチ、冪等キー、原文抜粋、全変更履歴
- ローカルAPIと3つのMCPツール
- Windowsショートカット作成、Codex Plugin導入スクリプト

## 運用前提

- 自宅のメインWindows PC 1台だけで使う
- データはPC内のSQLiteだけに保存する
- インターネット越しのアクセス機能は持たせない
- 複数PC・スマートフォンとの同期機能は持たせない
- 外部カレンダー・メール・クラウドサービスとは連携しない
- ChatGPT / Codexから明示的な合言葉で送られた活動だけを管理する

## アーキテクチャ

```text
ChatGPT / Codex conversation
  └─ explicit passphrase
       └─ sync-activity Skill
            ├─ search_activities
            ├─ get_sync_status
            └─ sync_activity
                 └─ http://127.0.0.1:8765
                      └─ SQLite + history + review queue
                           └─ Windows desktop UI
```

アプリを正本とし、LLMは活動候補の抽出、アプリは重複判定・安全判定・履歴・自動整理を担当します。会話全文は保存せず、同期対象の要約と必要最小限の原文抜粋だけを保持します。

## データモデル

| テーブル | 役割 |
|---|---|
| `items` | 現在のタスク・予定・アイデア、所属／親プロジェクト、工数、自動優先度と算出理由 |
| `sync_batches` | 1回の同期単位と冪等キー |
| `activity_events` | 作成・更新・完了などの不変履歴 |
| `review_queue` | 人が承認・却下する曖昧な変更 |
| `notification_log` | 同じ期限通知の重複防止 |

状態は `inbox / today / next / in_progress / waiting / someday / done / cancelled` です。

## アプリのセットアップ

1. GitHubの「Code」からZIPをダウンロードして展開するか、次のコマンドで取得します。

```powershell
git clone https://github.com/tuneken2/activity-compass.git
cd activity-compass
```

2. PowerShellで起動します。Codex同梱Python、`py`、`python` の順に自動検出します。

```powershell
.\run.ps1
```

画面はWindows標準のHTAで開き、保存APIだけをPythonでバックグラウンド起動します。追加のGUIライブラリは不要です。
最小化または右上の「×」でタスクトレイに収まり、トレイアイコンのダブルクリックで再表示できます。完全に終了する場合は、画面左側またはトレイアイコンの右クリックメニューから「終了」を選びます。

3. 任意でデスクトップ、スタートメニュー、スタートアップにショートカットを作成します。

```powershell
.\setup-windows.ps1
```

データは既定で `%LOCALAPPDATA%\ActivityCompass\activity.db`、バックアップはその下の `backups` に保存されます。開発時に場所を変えるには `ACTIVITY_COMPASS_DB` を設定します。

## Codexとの連携

個人マーケットプレイスへPluginを追加する準備スクリプトです。既存Pluginは上書きしません。

```powershell
.\install-plugin.ps1
```

追加後はCodexを再起動し、新しいタスクで利用します。アプリを先に起動してから、正式コマンドまたは短縮コマンドを送ります。

## Claude Codeとの連携

Claude Codeのインストールと認証を済ませてから、PowerShellで次を実行します。

```powershell
.\install-claude.ps1
```

このスクリプトは次の安全なユーザー設定だけを追加します。

- `~/.claude/skills/sync-activity/SKILL.md` に同期Skillをコピー
- `~/.claude/integrations/activity-compass/mcp-server.ps1` にローカルMCPサーバーをコピー
- `activity-compass` MCPをClaude Codeのユーザースコープに登録

同名のSkill、連携フォルダー、MCPがある場合は上書きせず停止します。認証情報や活動データはコピーしません。

設定後はActivity Compassを起動し、Claude Codeを再起動してください。Claude Codeで `/mcp` を開いて `activity-compass` の接続を確認した後、正式コマンドまたは短縮コマンドを送ります。Skillは `/sync-activity` でも明示的に呼び出せます。

Claude Codeにセットアップを任せる場合は、リポジトリ同梱の [`CLAUDE_SETUP_PROMPT.txt`](CLAUDE_SETUP_PROMPT.txt) を新しいClaude Codeセッションへ貼り付けてください。既存設定を上書きしない確認手順も含まれています。

### 手動設定

自動スクリプトを使わない場合は、次の2点を設定します。

1. `plugins/activity-sync/skills/sync-activity/SKILL.md` を `~/.claude/skills/sync-activity/SKILL.md` へコピーする。
2. MCPサーバーをユーザースコープへ登録する。

```powershell
claude mcp add --transport stdio --scope user activity-compass -- powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\任意の保存先\mcp-server.ps1"
claude mcp get activity-compass
```

`mcp-server.ps1` には `plugins/activity-sync/scripts/mcp-server.ps1` を使用します。登録後にActivity Compassが起動していないと同期は失敗します。

## 使い方

1. Activity Compassを起動したままにする。
2. CodexまたはClaude Codeで、タスク・予定・決定などを含む会話を進める。
3. 同期したい時点で正式コマンドまたは短縮コマンドを送る。
4. アプリの「今日」「次」「確認待ち」「更新履歴」などで結果を確認する。
5. 曖昧な完了・取消・延期・期限変更は「確認待ち」で承認または却下する。

接続できない場合は、アプリを起動し直してから同じ合言葉をもう一度送ってください。

### プロジェクト画面

アプリを起動すると、最初にプロジェクト画面が開きます。

- プロジェクト行をクリックすると、そのプロジェクトに所属するタスクを直下へ展開します。もう一度クリックすると折りたたみます。
- 画面右上の選択欄から「優先度順」「親プロジェクト順」「更新順」に並べ替えられます。
- プロジェクトの詳細ではカテゴリー名だけを設定します。カテゴリー色は自動で決まり、同名カテゴリーですべて統一されます。
- 各プロジェクトには重複しないイメージカラーが自動で割り当てられ、一覧の左端とタイトル横の丸印に表示されます。カテゴリー色はカテゴリー名のバッジに表示されます。
- 展開されたタスクは、優先度が高いもの、期限が近いものの順に表示されます。
- プロジェクトを選択すると詳細を確認・編集できます。タスクを選択した場合も通常の項目と同様に詳細を編集できます。

## 個人データと公開範囲

- 活動DB、バックアップ、書き出しJSONはリポジトリ外の `%LOCALAPPDATA%\ActivityCompass` に保存されます。
- `*.db`、`data/`、`.env*`、ローカルClaude設定、WindowsショートカットはGitの追跡対象外です。
- リポジトリにはサンプルの認証情報や個人活動データを含めていません。
- MCPサーバーは `127.0.0.1:8765` だけへ接続し、外部公開しません。

## テスト

プロジェクト直下で実行します。

```powershell
$env:PYTHONPATH = Join-Path $PWD "app"
py -3 -m unittest discover -s tests -v
```

`py -3` が使えない環境では、同じ引数でPython 3.10以上の実行ファイルを指定してください。

## ローカルAPI

- `GET /health`
- `GET /v1/items?view=today`
- `GET /v1/items?q=検索語`
- `GET /v1/history`
- `POST /v1/items`
- `POST /v1/items/{id}`
- `POST /v1/items/{id}/status`
- `POST /v1/sync`
- `POST /v1/reviews/{id}/approve`
- `POST /v1/reviews/{id}/reject`

APIは `127.0.0.1:8765` のみにバインドします。

## リポジトリ構成

```text
activity-compass/
├─ desktop.hta             Windows標準デスクトップ画面
├─ app/activity_compass/
│  ├─ db.py          SQLite、同期、安全判定、検索、履歴
│  ├─ api.py         ローカルHTTP API
│  ├─ automation.py  日次整理とバックアップ
│  ├─ ui.py          将来のPython GUI用実装
│  └─ main.py
├─ plugins/activity-sync/
│  ├─ skills/sync-activity/
│  ├─ scripts/mcp-server.ps1
│  └─ .mcp.json
├─ tests/
├─ run.ps1
├─ setup-windows.ps1
├─ install-plugin.ps1
├─ install-claude.ps1
└─ CLAUDE_SETUP_PROMPT.txt
```

## 次段階

1. 実会話20〜30件で抽出漏れ・誤更新を記録
2. 確信度閾値と重複候補の照合精度を調整
3. 自宅PCで迷わず起動できる単一EXE化

## ライセンス

[MIT License](LICENSE)
