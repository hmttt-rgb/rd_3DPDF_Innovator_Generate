# タスクスケジューラ

このディレクトリには、タスクスケジューラの XML エクスポートファイルを格納しています。  
フォルダごとに説明を追記できるよう、`pk6513` と `pkv0198` の単位で整理しています。

## フォルダ構成

- `pk6513/`
- `pkv0198/`

---

## pk6513

### フォルダ説明

> マニュアル版(Innovatorを介さない)の3DPDF生成プログラムについて、2DPDFの生成を実行/強制終了するタスク
pkv0198(3DPDF生成サーバー)から開始の指示をする。

### タスク一覧

| XMLファイル | タスク名 | 説明 |
|---|---|---|
| `create_2DPDF.xml` | `\create_2DPDF` | "16_3DPDF_fromVM"にある3DPDFを一つずつ開き、2DPDFを"10_TEMP"フォルダに格納する。最後にpkv0198の"08_TEMP_2DPDF"へ生成物コピーする(=2DPDF生成完了トリガー)。|
| `kill_acrobat.xml` | `\kill_acrobat` | 2DPDF生成時に異常が生じ、pkv0198の"08_TEMP_2DPDF"に10分間何も出力されなかった場合に実行される。強制的にタスクスケジューラcreate_2DPDFを終了させる。|

---

## pkv0198

### フォルダ説明

> 自動版(Innovatorから生成する)3DPDF生成プログラムに必要なタスクスケジューラー

### タスク一覧

| XMLファイル | タスク名 | 説明 |
|---|---|---|
| `Generate_3DPDF.xml` | `\Generate_3DPDF` | Innovatorからの3DPDF生成リクエストを受け付けるAPIを実行するタスク。pkv0198の起動時・ユーザー'kz121632'のログイン時に実行|
| `exec_SmartExchange_batch.xml` | `\exec_SmartExchange_batch` | SmartExchange実行用タスク。|
| `forced_end.xml` | `\forced_end` | 3DPDF,2DPDF生成中にエラーが発生した際に、実行中のSmartExchange(3DPDF)もしくはAdobe(2DPDF)を強制終了するプログラム。|
