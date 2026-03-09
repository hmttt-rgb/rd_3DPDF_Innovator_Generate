"""
内藤さんのプログラムに必要なパラメータを渡すプログラム.exe
↓
10秒待つ(検証中)
↓
Web形式の最終更新者設定プログラム

<パラメータ>
1. 社員番号
2. CAD ドキュメント番号： {cn} + "_DRS01"
3. ファイル名          : S6.py よりreturn
4. ファイル(フルパス)  ： INVフォルダ内の.pdfすべて
"""
import os
import time
import logging
import sqlite3
import requests
import subprocess

from ERROR import ERROR_main

from dotenv import load_dotenv
load_dotenv()
UPLOAD_URL = os.getenv("UPLOAD_URL") 


# ジョブDBに状況を送る
def send_condition(db_path, job_id, key_name):
    conn = sqlite3.connect(db_path, timeout=30.0)
        
    # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
    # これにより「読み込み」と「書き込み」が同時にできるようになります
    conn.execute('PRAGMA journal_mode=WAL;')
    
    cursor = conn.cursor()
    status = (key_name, job_id)

    try:
        cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
        conn.commit()
        logging.info(f"[!]  Updated Job Condition -> {key_name}")
    except Exception as e:
        error_msg = f"{e}(S7)"
        ERROR_main(db_path, job_id, error_msg, g_cadno, g_user_id)
        return None 
    finally:
        conn.close()


g_cadno = None
g_user_id = None
def S7_main(db_path, job_id, pdf2_name, pdf3_name, inv_folder, user_id, cadno, cn_path):
    
    global g_cadno
    global g_user_id
    
    g_cadno = cadno
    g_user_id = user_id


    status = 'Upload to INV'
    send_condition(db_path, job_id, status) # ジョブDBに "Upload to INV" と送る

    ## ファイル作成結果
    create_file_result = "OK"

    ## ファイルフルパス
    pdf_2d_path =  os.path.join(inv_folder, pdf2_name)
    pdf_3d_path =  os.path.join(inv_folder, pdf3_name)

    # upload_params = " ".join(map(str, params)) # すべてをstrにして、半角スペースで連結
    
    ## 3DPDFアップロードプログラムを呼び出す
    exe_path = r"C:\3DPDF\13_FileUploadProgram\ArasCadViewUpload_Rodend.exe"

    ## ログファイルパス
    log_path = os.path.join(cn_path, "LOG") + "\\"
    #print(log_path)

    # 以下のような形でプログラムを実行
    # ArasCadViewUpload_Rodend.EXE -B test_cad1 C:\Temp\test1.pdf C:\Temp\test2.pdf OK

    logging.info("pdf_2d_path ------")
    logging.info(pdf_2d_path)
    logging.info("pdf_3d_path ------")
    logging.info(pdf_3d_path)
    
    cmd = [
        exe_path,
        "-B",
        cadno, 
        pdf_2d_path,
        pdf_3d_path,
        create_file_result,
        log_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if result.returncode == 0: # 正常終了
            logging.info("3DPDF Upload Program Executed Successfully.(OK)")
        else: # 異常終了
            error_msg = f"3DPDF Upload Program Execution Error (S7)."
            ERROR_main(db_path, job_id, error_msg, cadno, g_user_id)

    except Exception as e: 
        error_msg = f"{e}(S7)"
        ERROR_main(db_path, job_id, error_msg, cadno, g_user_id)
    
    # 5秒待つ
    time.sleep(4)
    
    ## Web形式の最終更新者設定プログラムを呼び出す
    # 本番環境
    url = rf"http://{UPLOAD_URL}/Aras_RD_CAD/LastUserSv?userid={user_id}&cadno={cadno}"
    
    # TODO
    response = requests.get(url)
    if response.status_code == 200:
        status = 'Completed'
        send_condition(db_path, job_id, status) # ジョブDBに "Completed" と送る
    else:
        error_msg = f"Last Updater Setting Program Execution Error (S7)."
        ERROR_main(db_path, job_id, error_msg, cadno, g_user_id)
    