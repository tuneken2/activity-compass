---
name: sync-activity
description: Extract activity changes from the current conversation and send them to Activity Compass (also called AC or アクコン) through its MCP tool. Use when the user explicitly says 「ここまでの活動情報を管理アプリに反映して」, 「活動管理に反映して」, 「アクコンに追加して」, 「ACに追加して」, or an equally explicit request to add or reflect the current conversation's activity in Activity Compass by its full name or alias. Treat 「アクコンに追加して」 and 「ACに追加して」 as complete explicit sync requests even when they do not separately mention the current conversation or activity information. Do not invoke merely because AC or アクコン is mentioned, for generic words such as 「同期」「保存」「記録」「更新」 without a destination, when discussing or quoting a trigger phrase, or when designing the sync feature itself.
---

# Activity Compassへ同期

現在の会話で新規作成・変更・確定された活動情報だけを抽出し、`activity-compass` MCPの `sync_activity` を1回呼ぶ。

`AC`と`アクコン`は、Activity Compassの略称として扱う。

## 抽出する

- `task`: 実行可能な行動
- `schedule`: 日時がある予定
- `idea`: 未確定の着想
- `waiting`: 他人・日付・条件を待つもの
- `decision`: 採用された判断
- `project`: 複数行動を含む継続プロジェクト

各イベントに `action`, `entity_type`, `title`, `confidence` を必ず付ける。分かる場合だけ `details`, `due_at`, `scheduled_at`, `status`, `project_id`, `project_title`, `parent_project_id`, `project_rank`, `category`, `category_color`, `effort`, `target_id`, `source_excerpt` を付ける。

- 着手済みで完了していない活動には `status: "in_progress"` を付ける。
- タスク等の所属プロジェクトが会話から分かる場合は、検索でIDを確認できれば `project_id`、確認できなければ `project_title` を付ける。
- プロジェクト自体に親プロジェクトがある場合は `parent_project_id` を付ける。
- プロジェクトのカテゴリーが明示されている場合は `category` を付ける。色も明示されている場合だけ `category_color` を `#RRGGBB` 形式で付ける。同名カテゴリーの既存色はアプリが再利用する。
- 実装難易度・工数が分かる場合は `effort` を1（小）〜5（大）で付ける。
- `priority` はプロジェクトの運用優先度を明示的に登録・変更する場合だけ送る。通常のタスク優先度はアプリが所属プロジェクト、期限、工数から自動算出する。
- `priority` は数字の `3`（高）、`2`（中）、`1`（低）で送る。
- `project_rank` は同一優先度内でのプロジェクトの序列を1始まりの正整数で送る。1が先頭。省略時は同じ優先度の末尾に追加される。

`action` は `create`, `update`, `complete`, `cancel`, `defer`, `note` のいずれかにする。

## 除外する

- 一般論、説明のための例、仮定、検討しただけの案
- アシスタントだけが提案し、ユーザーが採用していない内容
- 否定・撤回された案
- 既存情報の単なる言い直し
- 活動管理に不要なセンシティブ情報

## 手順

1. 発動依頼そのものを除き、現在の会話で確定・変更された活動を列挙する。
2. 同じ対象への複数言及を最新状態へまとめる。
3. プロジェクトまたはタスクを抽出したら、`search_activities` で短い固有語を検索する。既存項目と判断できる場合は新規作成せず、実際の種類を維持して `action: "update"` と `target_id` を付ける。完全一致しない場合でも表記差（「プロジェクト」「タスク」の有無など）を考慮し、候補が一意でない場合は推測で更新しない。
4. タイトルは抽象語ではなく、次の行動または識別可能な案件名にする。
5. 日付は会話の基準日とタイムゾーンを使ってISO 8601へ正規化する。推測した日付は確信度を下げる。
6. 完了、取消、延期、期限・予定日時の変更は、明示されていなければ `confidence` を0.89以下にする。アプリ側が確認待ちにする。
7. 会話IDと最終対象メッセージIDを取得できる場合は `idempotency_key` を `conversation:<id>:through:<message-id>` とする。取得できなければ省略する。
8. `source_summary` は同期内容の1文要約にする。会話全文は送らない。
9. `sync_activity` をイベント配列ごと1回だけ呼ぶ。イベントがなくても空配列で呼ぶ。
10. 成功後は「新規N件、更新N件、確認待ちN件」のみを簡潔に報告する。
11. 失敗時は、Activity Compassを起動してから同じ合言葉をもう一度送るよう明記する。

## 送信例

```json
{
  "source": "chatgpt",
  "source_summary": "管理アプリMVPの実装開始を決定",
  "events": [
    {
      "action": "create",
      "entity_type": "project",
      "title": "Activity Compass MVP",
      "details": "会話から合言葉で活動情報を同期するWindowsアプリ",
      "status": "next",
      "confidence": 0.98,
      "source_excerpt": "実際の制作に入りたい"
    }
  ]
}
```
