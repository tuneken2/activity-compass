---
name: add-task
description: Trigger automatically, without any passphrase, when the user's message is by itself an obvious task entry — a short task name/title, optionally followed by details such as a due date, memo, or project — rather than ordinary conversation. Immediately create exactly one task in Activity Compass through the activity-compass MCP tool, filling in a missing due date, project, or status only when the text itself makes them clear. Do not invoke for questions, requests for opinion, discussion, hypotheticals, casual mentions of a task inside a larger conversation, restatements of an existing task with no new information, or discussion of this sync/add-task feature itself.
---

# タスクを1件だけ即時追加

会話として書かれた文ではなく、タスク登録欄に直接書き込むような単独の入力（タスク名、または「タスク名＋補足」）を認識し、合言葉なしでその場でActivity Compassへ1件だけ作成する。複数の活動をまとめて反映する`sync-activity`とは別の、単発タスクの即時取り込み専用の手段。

## 発動条件

次のいずれかに当たる、それ単体で完結した入力のときだけ発動する。

- 短い名詞・動詞フレーズ1行だけの入力（例:「資料作成」「請求書を出す」「〇〇さんに確認の連絡」）
- 上記のようなタスク名の行に、期限・メモ・所属プロジェクトなどの補足が続く入力。改行区切り、読点区切り、「タスク：」「TODO：」のような見出し付きのいずれでもよい

次のような入力では発動しない。発動条件に迷う場合も発動せず、通常の会話として応答する。

- 質問、相談、感想、説明を求める文
- 既にあるタスクの状況を述べただけで新しい情報がない文
- 「〜しようかな」のような未確定の思いつき
- 一般的な会話の中で話題としてタスクに触れているだけで、登録欄への入力のような単独性がない文
- このSkillや`sync-activity`、Activity Compassの仕組み自体についての会話

## 抽出と補完

1. タスク名を先頭行または見出し直後の語句から抜き出す。抽象語ではなく次の行動または識別できる案件名にする。
2. 残りの文があれば`details`に入れる。
3. 期限・予定日が本文の表現から読み取れる場合だけ、会話の基準日とタイムゾーンを使ってISO 8601の`due_at`に正規化する。「明日」「来週まで」「月末」のような相対表現からの推測は`confidence`を下げる。本文に時期の言及が一切ない場合は`due_at`を付けない。
4. 緊急度を表す言葉があれば`status`を補う。「今日中」「すぐ」→`today`。「そのうち」「いつか」「落ち着いたら」→`someday`。該当する言葉がなければ`status`は付けず、既定の`inbox`のまま「次」に表示させる。
5. 所属プロジェクトが本文で明示されている場合、または既存プロジェクト名と一致・強く類似する場合だけ`search_activities`で確認する。確認できれば`project_id`、タイトルは分かるがIDが確認できなければ`project_title`を付ける。曖昧なら何も付けない。
6. `entity_type`は常に`task`、`action`は常に`create`にする。同名の既存タスクがあればアプリ側が重複作成せず追記に切り替えるため、事前の重複確認は不要。
7. `confidence`は0.9を基準にする。期限や所属プロジェクトを推測で埋めた場合は0.8程度まで下げる。
8. `source_excerpt`に入力文そのものを入れる。`source_summary`は「タスクを1件追加」のような短い要約にする。`idempotency_key`は会話IDと対象メッセージIDが取得できる場合だけ付け、取得できなければ省略する。
9. `sync_activity`をイベント1件だけの配列で1回呼ぶ。

## 報告

成功したら、追加したタスク名と、補完できた期限・所属プロジェクト・ステータスだけを1〜2文で簡潔に報告する。既存タスクへの追記になった場合はその旨を伝える。接続に失敗した場合は、Activity Compassを起動してから同じ入力をもう一度送るよう案内する。

## 例

入力:

```text
資料作成
来週金曜までに提出用の資料をまとめる
```

送信:

```json
{
  "source": "claude-code",
  "source_summary": "タスクを1件追加",
  "events": [
    {
      "action": "create",
      "entity_type": "task",
      "title": "資料作成",
      "details": "提出用の資料をまとめる",
      "due_at": "2026-08-14",
      "confidence": 0.85,
      "source_excerpt": "資料作成\n来週金曜までに提出用の資料をまとめる"
    }
  ]
}
```
