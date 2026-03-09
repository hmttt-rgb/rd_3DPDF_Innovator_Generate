# 3DPDF_Generate

3DPDF and 2DPDF automatically upload from Innovator by using registered Innovator data (Process Information, CATIA Native Files, etc...).

This repository is the **single source of truth** for disaster recovery. Anyone with access to this repo must be able to rebuild the entire environment from scratch.

---

## Repository Structure

```
3DPDF_Generate/
├── env-setup/                     # Environment rebuild configs
│   ├── gpu-dda/                   # Windows GPU (DDA) settings
│   ├── app-configs/               # Application configuration templates
│   ├── shared-folders/            # Network share definitions
│   └── task-scheduler/            # Windows Task Scheduler XML exports
├── src/
│   ├── auto-generator/            # Innovator client → API request sender
│   ├── manual-generator/          # Manual job submission tool
│   ├── api/                       # API server (pkv0199 / pkv0198)
│   └── job-manager/               # Server-side job orchestrator
└── docs/
    ├── operations-log.md          # Operational history
    └── troubleshooting-log.md     # Troubleshooting history
```

---

## System Overview

### Server

| Role | Hostname |
|------|----------|
| Primary generation server | pkv0199 |
| Secondary generation server | pk6513 |

*pk6513は手動版に用いられる、2DPDF生成専用のサーバーである。
 (図面画質問題に対処するため)
 
### System Flow

```mermaid
flowchart LR
    subgraph UserPC ["ユーザーPC"]
        InnovatorApp["Innovator<br/>(Webアプリ)"]
        JobStatusApp["ジョブ状況確認アプリ"]
    end

    subgraph Server ["サーバー (pkv0198)"]
        APIServer["API<br/>(サーバー：pkv0198)"]
        JobDB[("Job管理DB<br/>(サーバー：pkv0198)")]
        GeneratePDF["3DPDF生成プログラム"]
        UploadFile["ファイルアップロード<br/>プログラム"]
    end

    InnovatorServer["Aras Innovator<br/>Server"]

    %% 処理開始フロー
    InnovatorApp -->|"アクションボタン:<br/>リクエスト送る"| APIServer
    APIServer -->|"Jobの登録"| JobDB

    %% 非同期ステータス確認フロー
    JobStatusApp <-->|リクエスト / Job状況| APIServer
    APIServer <--> JobDB

    %% バックエンド処理フロー
    APIServer -->|生成指示| GeneratePDF
    GeneratePDF <-->|"Jobの更新"| JobDB
    GeneratePDF -->|"Batch/xml生成<br/>3D/2D生成<br/>マージ"| UploadFile
    UploadFile -->|"ファイルをアップロード"| InnovatorServer
    UploadFile -.->|"完了/エラー通知"| InnovatorApp
```

---

## 2D/3DPDF Job Sequence

```mermaid
flowchart TD
    Start([生成開始]) --> CreateID[job_id 作成]
    CreateID --> Status1["JobDB送信<br/>'Queued'"]

    subgraph Program_Logic ["3DPDF生成プログラム内部処理"]
        Status1 --> GetInfo["1. クエリ<br/>(SQLで工程情報取得)"]
        GetInfo --> Status2["JobDB送信<br/>'Processing xml'"]
        
        Status2 --> CheckAuth["2. Security<br/>(ユーザー権限確認)"]
        CheckAuth --> Download["3. File Vault<br/>(CATIA native file DL)"]
        
        Download --> XMLGen["4. xml<br/>(xml生成・ログ作成)"]
        XMLGen --> Status3["JobDB送信<br/>'Waiting 3DPDF'"]
        
        Status3 --> PDF3D["5. 3DPDF生成<br/>(CATIA/DDA経由)"]
        PDF3D --> Status4["JobDB送信<br/>'Waiting 2DPDF'"]
        
        Status4 --> PDF2D["6. 2DPDF生成"]
        PDF2D --> Status5["JobDB送信<br/>'Merging 2DPDF'"]
        
        Status5 --> Merge["7. 2DPDF Merge<br/>(PDF完了)"]
        Merge --> Status6["JobDB送信<br/>'Waiting for file upload'"]
    end

    subgraph Upload_Process ["ファイルアップロード処理"]
        Status6 --> Upload["Innovatorへアップロード"]
    end

    %% エラーハンドリング
    Program_Logic -- "異常発生" --> ErrorStatus["JobDB送信<br/>'Error: 内容を記録'"]
    Upload_Process -- "失敗" --> ErrorStatus
    
    %% 完了
    Upload -- "成功" --> DoneStatus["JobDB送信<br/>'Done'"]

    %% 注釈
    ErrorStatus -.-> InnovatorNotice["Innovator/状況確認アプリへ<br/>エラー内容を即時通知"]
    DoneStatus -.-> InnovatorNoticeSuccess["完了通知"]

    style ErrorStatus fill:#f96,stroke:#333
    style DoneStatus fill:#9f9,stroke:#333
```

---

## Job Status Reference

| Status | Description |
|--------|-------------|
| `Queued` | Job accepted by the API, waiting in queue |
| `Processing 3DPDF` | CATIA is actively generating the 3DPDF |
| `Waiting for file upload` | PDF generated, uploading to Innovator |
| `Done` | Completed successfully |
| `Error` | Failed — check `error_message` in the job record |

---

## Disaster Recovery — Rebuild Checklist

1. **Environment Setup** → See [`env-setup/README.md`](env-setup/README.md)
   - [ ] GPU (DDA) assigned to VM — [`env-setup/gpu-dda/README.md`](env-setup/gpu-dda/README.md)
   - [ ] App configs deployed — [`env-setup/app-configs/README.md`](env-setup/app-configs/README.md)
   - [ ] Shared folders created — [`env-setup/shared-folders/setup.md`](env-setup/shared-folders/setup.md)
   - [ ] Task Scheduler tasks imported — [`env-setup/task-scheduler/README.md`](env-setup/task-scheduler/README.md)
2. **Deploy Source Code** → clone this repo to `C:\3DPDF\` on the server
3. **Configure Applications** → copy `config.example.json` → `config.json` and fill in credentials
4. **Start Services** → Task Scheduler tasks will start the API and Job Manager automatically on next boot, or start manually via Task Scheduler

---

## Documentation

- [Operations Log](docs/operations-log.md)
- [Troubleshooting Log](docs/troubleshooting-log.md)
