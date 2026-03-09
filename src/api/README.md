# API Server

## 概要

- **サーバー名**: [API_BASE_URL]参照のこと
- **言語**: Python
- **ポート番号**: [API_PORT]参照のこと
- **役割**: 3DPDF 生成リクエストの受付、生成プログラムのキック、および生成状況（ジョブ）の管理・回答を行う API ゲートウェイサーバー

ユーザー PC や Innovator サーバーとは別のサーバー（pkv0198）上で、リクエストした 3DPDF の生成状況をリアルタイムで確認できるようにすることを目的としている。

## 起動メカニズム

タスクスケジューラにより以下の順序で起動される。

```
タスクスケジューラ → .vbs ファイル → バッチファイル(.bat) → Python 実行
```

## エンドポイント仕様

Manual_Generate(Innovatorを介さない手動実行版)は **POST** メソッドで受け付け、
それ以外のプログラムは**GET** メソッドで受け付ける。

### 3DPDF 生成

| エンドポイント | 説明 |
|---|---|
| `/api/generate_3dpdf_v1_2` | 図面 v1.20 の 3DPDF を生成する |
| `/api/generate_3dpdf_v1_3` | 図面 v1.30 の 3DPDF を生成する |

**クエリパラメータ:**

| パラメータ | 説明 |
|---|---|
| `key` | API キー |
| `cadno` | CAD ドキュメント番号 |
| `userid` | ユーザー ID |

**リクエスト例:**

```
GET http://[API_URL]:[API_PORT]/api/generate_3dpdf_v1_2?key=<APIキー>&cadno=<CADドキュメント番号>&userid=<ユーザーID>
```

**動作:**
URL から抽出した引数を、`\\[3DPDF生成サーバ]\3DPDF\99_3DPDF_generate\exe` に格納された本体プログラムに渡して実行する。

### ジョブ確認

| エンドポイント | 説明 |
|---|---|
| `/api/job_check` | ジョブの進捗状況を確認する |

**クエリパラメータ:**

| パラメータ | 説明 |
|---|---|
| `key_gui` | API キー |

**リクエスト例:**

```
GET http://[API_URL]:[API_PORT]/api/job_check?key_gui=<APIキー>
```

**動作:**
API サーバーが直接 `job.db` に対してクエリを実行し、状況を JSON 形式で返却する。

## データベース仕様 (job.db)

ジョブの進捗管理を行う `job` テーブルの定義。

| カラム名 | 説明 |
|---|---|
| `date` | プログラム開始時間（API リクエスト取得後、処理を開始した時間） |
| `userid` | API リクエスト送信者（実行ユーザー） |
| `cn` | 生成対象の部品コントロール番号 (Control Number) |
| `status` | 進捗ステータス |
| `condition` | 終了状態。エラー発生時は `Failed` と表示 |

## ステータス遷移

ジョブの進捗は以下の順序で遷移する。

```
Queued
  ↓
Creating xml file(s)
  ↓
Waiting for 2DPDF
  ↓
Processing 2DPDF      ※ 1アカウントのみ実行可能
  ↓
Waiting for 3DPDF
  ↓
Processing 3DPDF      ※ 1アカウントのみ実行可能
  ↓
Merging 2DPDF(s)
  ↓
Upload to INV
  ↓
Completed
```

## 運用上の重要事項

### 同時実行の制御

- `Processing 2DPDF` と `Processing 3DPDF` の工程は、システム仕様上 **1 アカウント（1 プロセス）のみ** 実行可能。
- その他の工程は複数アカウントでの同時実行が可能。

### Innovator 連携の制約

- Innovator 側からは **URL のみ** で外部アプリを呼び出す仕様となっている。
- そのため、引数はすべてクエリパラメータ（URL の末尾）に含める必要がある。

### ユーザー PC からの利用

- ジョブ確認（ステータスチェック）については、ユーザー PC から直接 API を呼び出す構成となっている。

## ディレクトリ構成

```
api/
├── README.md           ← このファイル
├── main.py             ← ソースコード
├── start_api.bat       ← API起動用バッチ
└── run_bat.vbs         ← バッチを裏で実行するためのvbsファイル (タスクスケジューラー呼び出し元)
```
