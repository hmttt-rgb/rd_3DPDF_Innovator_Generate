import os
import sqlite3
import uvicorn
import subprocess # .exe 実行のために追加
from pydantic import BaseModel # POSTリクエストの本体を受け取るために追加
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, Depends, Header, Query, HTTPException

from dotenv import load_dotenv
load_dotenv()

# 3DPDF生成プログラム呼び出し用
API_URL = os.getenv("API_URL")

# JOBステータス確認用
VALID_API_KEY = os.getenv("VALID_API_KEY")

# ポート番号
PORT = os.getenv("PORT")


# 接続するジョブ管理DB
# 本番
DB_PATH = r"C:\3DPDF\99_3DPDF_generate\job.db"


# 3DPDF生成プログラム (テスト：社内規格DLするやつ)
#EXE_PATH = r"C:\Users\kz121632\Desktop\COMSPEC_KEYWORD_DL.exe"
EXE_PATH = r"C:\3DPDF\99_3DPDF_generate\exe\v2.0\3DPDF_gen_upload.exe"

# job.dbのテーブル名とカラム名
TABLE_NAME = "job"
COL_DATE = "date"
COL_CN = "cn"
COL_STATUS = "status"
COL_CONDITION = "condition"
COL_ERROR = "error"

# --- FastAPIアプリケーション ---

app = FastAPI()

# --- 認証 (APIキーのみ) ---
async def verify_api_key(x_api_key: str = Header(..., alias="X-Api-Key")):
    """
    APIキーのみを検証するDependency
    """
    if x_api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")
    return x_api_key


# --- APIエンドポイント ---
# 1. .exeを実行するAPI
# テンプレート図面 v1.2
@app.get("/api/generate_3dpdf_v1_2", response_class=HTMLResponse)
async def generate_3dpdf_get_v1_2(
    key: str,
    cadno: str,  
    userid: str,
):
    # APIキーを手動で検証
    if key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # .exeに渡す引数を準備
    ver = "v1.20"
    args = [EXE_PATH, cadno, userid, ver]
    exe_directory = os.path.dirname(EXE_PATH)
    try:
        # .exeを非同期で実行
        subprocess.Popen(args, cwd=exe_directory, creationflags=subprocess.CREATE_NEW_CONSOLE )
        
        # ポップアップウィンドウに表示するメッセージ
        return """
        <html>
            <head><title>実行中</title></head>
            <body>
                <p>ジョブを開始しました。このウィンドウは閉じてください。</p>
                <script>window.close();</script>
            </body>
        </html>
        """
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Error: {e}")


async def verify_api_key_gui(x_api_key_gui: str = Header(..., alias="X-Api-Key_GUI")):
    """
    APIキーのみを検証するDependency
    """
    if x_api_key_gui != VALID_API_KEY_GUI:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")
    return x_api_key_gui

class JobResponse(BaseModel):
    date: str
    cadno: str
    status: str
    condition: str
    error: str

# 2. .exeを実行するAPI
# テンプレート図面 v1.3
@app.get("/api/generate_3dpdf_v1_3", response_class=HTMLResponse)
async def generate_3dpdf_get_v1_3(
    key: str,
    cadno: str,  
    userid: str,
):
    # APIキーを手動で検証
    if key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # .exeに渡す引数を準備
    ver = "v1.30"
    args = [EXE_PATH, cadno, userid, ver]
    exe_directory = os.path.dirname(EXE_PATH)
    try:
        # .exeを非同期で実行
        subprocess.Popen(args, cwd=exe_directory, creationflags=subprocess.CREATE_NEW_CONSOLE )
        
        # ポップアップウィンドウに表示するメッセージ
        return """
        <html>
            <head><title>実行中</title></head>
            <body>
                <p>ジョブを開始しました。このウィンドウは閉じてください。</p>
                <script>window.close();</script>
            </body>
        </html>
        """
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Error: {e}")


async def verify_api_key_gui(x_api_key_gui: str = Header(..., alias="X-Api-Key_GUI")):
    """
    APIキーのみを検証するDependency
    """
    if x_api_key_gui != VALID_API_KEY_GUI:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")
    return x_api_key_gui

class JobResponse(BaseModel):
    date: str
    cadno: str
    status: str
    condition: str
    error: str


## 3. 【ステータス確認用】ジョブ一覧を取得するAPI
@app.get("/api/job_check")
async def get_jobs(
    key_gui: str
):
    # APIキーを手動で検証
    if key_gui != VALID_API_KEY_GUI:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # DBへの接続とクエリ実行
    limit = 15

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = """
    SELECT date, cn, status, condition, error
    FROM job
    ORDER BY date DESC 
    LIMIT ?
    """
    cursor.execute(query, (limit,))

    # クエリの結果をjson形式で返す
    jobs = []
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        jobs.append(dict(zip(columns, row)))
    conn.close()
    return jobs

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(PORT), reload=True)