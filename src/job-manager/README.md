# job_gui.py — 3DPDF Job Manager GUI

3DPDF 生成ジョブの状態を API から非同期取得し、**PyQt6 ベースのテーブル GUI** で可視化するデスクトップアプリケーション。

## 概要

- ジョブ一覧の最新状態を API から取得して表示する
- CN 文字列でジョブを検索する
- ステータス / コンディションに応じてセル背景色を変え、状況を視認しやすくする
- API 通信は別スレッド（`QThread`）で実行し、UI のフリーズを防止する
- リフレッシュ時の連打防止クールダウン（5 秒）を実装

---

## 動作環境・依存

| 種別 | 内容 |
|------|------|
| Python | 3.x |
| GUI フレームワーク | PyQt6 |
| 標準ライブラリ | `sys`, `json`, `urllib.request`, `urllib.parse`, `urllib.error`, `datetime` |

---

## ディレクトリ構成

```
job-manager/
├── README.md            ← 本ファイル
├── job_gui.py           ← メインアプリケーション
└── 3DPDF_JOB.spec       ← EXE作成時のSPECファイル
```

---

## 設定値

ファイル内に以下の固定値を持つ。

| 設定 | 説明 |
|------|------|
| `API_URL` | 本番 API エンドポイント（`key_gui` クエリ付き URL） |
| `VALID_API_KEY` | GUI 用 API キー |

> **補足**: コード上はテスト環境設定がコメントアウトされ、本番設定が有効になっている。`JobFetcher.run()` で `params` として `key_gui` と `cn` が付加される。

---

## 画面仕様

### ウィンドウ

| 項目 | 内容 |
|------|------|
| クラス | `JobManagerWindow` |
| タイトル | `3DPDF Job Manager` |
| 初期サイズ | `1000 x 600` |

### ヘッダ領域

| UI 要素 | 説明 |
|---------|------|
| タイトルラベル | `3DPDF Job Manager` |
| リフレッシュボタン | `🔄 Refresh` — クリック時に API 再取得を開始 |
| 検索入力 | プレースホルダ `Search CN...` — Enter 押下で検索実行 |
| 検索ボタン | `🔍 Search` — クリックで検索実行 |

### テーブル

| 列番号 | ヘッダ | 説明 |
|--------|--------|------|
| 1 | `Date(JST)` | UTC → JST 変換後の日時 |
| 2 | `CN` | 管理対象 CN |
| 3 | `Status` | 実行状態（色分けあり） |
| 4 | `Condition` | 条件/結果（色分けあり） |
| 5 | `Error` | エラー詳細（左寄せ、横幅ストレッチ） |

- 全セル編集不可
- 更新後に `resizeColumnsToContents()` で自動調整

### ステータスバー

画面下部ラベルに最終更新時刻・処理状態・エラー内容を表示。

---

## データ仕様

API 応答 JSON の各要素（ジョブ 1 件）は以下のキーを想定する。

| キー | 内容 | 欠損時 |
|------|------|--------|
| `date` | UTC 日時文字列（`%Y-%m-%d %H:%M:%S`） | `---` |
| `cn` | 管理対象 CN | `---` |
| `status` | 実行状態 | `---` |
| `condition` | 条件/結果（例: failed, cancel） | `N/A` |
| `error` | エラー詳細 | `N/A` |

---

## 処理フロー

### 起動時

1. `QApplication` 生成
2. `JobManagerWindow` 生成
3. UI 初期化（`_setup_ui`）
4. 初回データ取得（`start_fetch`）
5. ウィンドウ表示

### データ取得 (`start_fetch`)

1. 取得中フラグ `is_fetching` を確認
2. ボタン表示を `Loading...` に変更・無効化
3. ステータス表示を取得中メッセージへ更新
4. クールダウンタイマー開始（1 秒間隔、5 秒カウント）
5. `QThread` + `JobFetcher` を生成し、シグナル接続
6. スレッド起動

### API 通信 (`JobFetcher.run`)

1. パラメータを URL エンコード
2. `API_URL` へクエリ結合
3. `urllib.request.urlopen(timeout=10)` で取得
4. JSON をデコード
5. 成功時: `finished` シグナルでジョブ配列を返却
6. 失敗時: `error` シグナルへメッセージ送出

### 取得成功 (`on_fetch_success`)

1. 全ジョブを `self.all_jobs` に保存
2. 現在の検索語で `apply_filter()` を実行
3. `Last Update: YYYY-mm-dd HH:MM:SS` を更新

### 取得失敗 (`on_fetch_error`)

1. 警告ダイアログ表示
2. ステータス欄へエラーメッセージ表示
3. コンソール出力

### スレッド後処理 (`cleanup_thread`)

1. Worker / Thread を `deleteLater()`
2. 参照を `None` 化
3. `is_fetching = False`
4. リフレッシュボタンの文言と有効状態を復帰

---

## フィルタ仕様

| 項目 | 内容 |
|------|------|
| 対象フィールド | `cn` |
| 検索条件 | 小文字化した部分一致 |
| 検索語未入力時 | 全件表示 |

---

## 表示変換・装飾

### 日時変換

- `date` は UTC 文字列として解釈し、JST（UTC+9）へ変換して `Date(JST)` 列に表示
- 変換失敗時: `Date Parse Error: <元文字列>` または `Date Error: <例外>`

### セル背景色

| 列 | 条件 | 背景色 |
|----|------|--------|
| `Status` | `complete` を含む | 薄緑 `(200, 255, 200)` |
| `Status` | `running` を含む | 薄黄 `(255, 255, 200)` |
| `Condition` | `failed` を含む | 赤 `(255, 180, 180)` |
| `Condition` | `cancel` を含む | 黄 `(255, 255, 180)` |

### 文字寄せ

| 列 | 配置 |
|----|------|
| `Error` | 左寄せ + 垂直中央 |
| その他 | 中央寄せ |

---

## エラーハンドリング

`JobFetcher.run()` で以下の例外を捕捉し、ユーザー向けメッセージに変換して `error` シグナルで UI へ通知する。

| 例外 | 説明 |
|------|------|
| `urllib.error.HTTPError` | HTTP エラー応答 |
| `urllib.error.URLError` | ネットワーク接続エラー |
| `json.JSONDecodeError` | JSON パースエラー |
| `Exception` | その他の予期しないエラー |

---

## リフレッシュ制御

| 項目 | 値 |
|------|-----|
| クールダウン時間 | 5 秒 |
| タイマー周期 | 1 秒 |
| クールダウン中 | ボタン無効化、スタイルをグレーに変更 |
| クールダウン終了 | ボタン有効化、スタイルをデフォルトに復帰 |

---

## 既知の注意点

- `API_URL` に `key_gui` が既に含まれる一方、`params` でも `key_gui` を追加しており、同一キーが重複する構造になり得る。
- `HTTPError` 処理で `e.response.status_code` や `e.response.text` を参照しているが、`urllib` 標準の属性構造と一致しない可能性がある。
- API キーや URL がコード直書きのため、運用上は環境変数化が望ましい。
