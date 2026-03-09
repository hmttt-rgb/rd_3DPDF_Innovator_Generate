"""
エラー発生時の処理
1. DBのjobテーブルのconditionを 'Failed' に更新
2. エラーメッセージをDBに記録
3. 3DPDFアップロードプログラムに次のパラメータを明け渡す
    - userid (e.g. kz121632)
    - CADドキュメント番号 (e.g. F01-02096)
    - ファイル実行結果 "ERROR"
4. 3DPDFアップロードプログラムを呼び出す
5. プログラムを終了
"""

import os
import sys
import sqlite3
import logging
import requests
import subprocess

from dotenv import load_dotenv
# .envファイルから環境変数を読み込む
load_dotenv()
UPLOAD_URL = os.getenv("UPLOAD_URL")

# プロセスに応じた強制終了プログラム
# 1アカウント限定の処理で詰まるのを防ぐため

FORCED_END_BATCH = r"C:\3DPDF\98_3DPDF_Manual_Generate\batch_files\forced_end.bat"
FORCED_END_ORG = r"C:\3DPDF\98_3DPDF_Manual_Generate\orginal_batch\forced_end_org.bat"

def forced_end(db_path, job_id):
    #logging.error("START: forced_end")
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
        # これにより「読み込み」と「書き込み」が同時にできるようになります
        conn.execute('PRAGMA journal_mode=WAL;')
        
        cursor = conn.cursor()
        
        # 1. 現在のJob Conditionを確認
        cursor.execute('SELECT condition FROM job WHERE job_id = ?', (job_id,))
        result = cursor.fetchone()

        current_condition = result[0] if result else ""

        # タスクスケジューラーやバッチが働くプロセス(3DPDF生成など)でキャンセルされた場合
        if not current_condition == None:
            # タスクスケジューラーで強制終了バッチを働かせる
            with open(FORCED_END_BATCH, "w", encoding='cp932') as f:
                f.write('@echo off\n')
                f.write(f'{FORCED_END_ORG} {current_condition}')
            
            # 強制終了バッチを起動
            subprocess.run(FORCED_END_BATCH, check=True, shell=True)

            #logging.error("END: forced_end")

    except Exception as e:
        # エラー報告中にさらにエラーが起きた場合 (例: DBがロックされている)
        logging.error(f"Failed to Change Condition: {e}")
        


def job_error(db_path, job_id: str, error_msg: str):
    """
    1. DBのjobテーブルのconditionを 'Failed' に更新
    2. エラーメッセージをDBに記録
    """
    conn = None
    #logging.error("START: job_error")
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        
        # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
        # これにより「読み込み」と「書き込み」が同時にできるようになります
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()

        
        # 1. Conditionを 'Failed' に設定
        # 2. エラーメッセージを記録
        cursor.execute('''
            UPDATE job 
            SET condition = ?, error = ? 
            WHERE job_id = ?
        ''', ('Failed', str(error_msg), job_id))

        conn.commit()
        #logging.error("END: job_error")

    except Exception as e:
        # エラー報告中にさらにエラーが起きた場合 (例: DBがロックされている)
        logging.error(f"Failed to Report ERROR: {e}")
        logging.error(f"Original Error Message: {error_msg}")
        

def ERROR_main(db_path, job_id: str, error_msg: str, cadno, user_id):
    conn = None
    try:

        # プロセスに応じた強制終了バッチを起動
        
        forced_end(db_path, job_id)
        
        # DBの更新
        job_error(db_path, job_id, error_msg)


        # エラーメッセージをログに表示
        logging.error(error_msg)

        ## CADドキュメント番号、社員番号, ファイル作成結果
        create_file_result = "ERROR"

        ## ファイルフルパス(実質不要なので仮で"ERROR"を入れる)
        pdf_2d_path = "ERROR"
        pdf_3d_path = "ERROR"

        ## 3DPDFアップロードプログラムを呼び出す
        exe_path = r"C:\3DPDF\13_FileUploadProgram\ArasCadViewUpload_Rodend.exe"

        ## ログファイルパス
        log_path = r"C:\3DPDF\21_LOG" + "\\"

        # パラメータの作成
        # 以下のような形でプログラムを実行
        # ArasCadViewUpload_Rodend.EXE -B test_cad1 C:\Temp\test1.pdf C:\Temp\test2.pdf OK    
        cmd = [
            exe_path,
            "-B",
            cadno,
            pdf_2d_path,
            pdf_3d_path,
            create_file_result,
            log_path
        ]
        # print("ERROR Emerged!")


        # 3DPDFアップロードプログラムの呼び出
        #TODO
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.returncode == 0: # 正常終了
                logging.info("3DPDF Upload Program Executed Successfully (ERROR).")

            else: # 異常終了
                logging.error("3DPDF Upload Program Execution Error (S7).")


        except Exception as e: 
            error_msg = f"{e}(S7)"
            logging.error(f"Failed to execute 3DPDF Upload Program: {error_msg}")

        # 最終更新者をAdminではなく、実行者本人にするプログラム
        # 本番環境
        url = rf"http://{UPLOAD_URL}/Aras_RD_CAD/LastUserSv?userid={user_id}&cadno={cadno}"
        
        # TODO
        response = requests.get(url)
        if response.status_code == 200:
            logging.info("Last Updater Setting Program Executed Successfully (ERROR).")
        else:
            logging.info(f"Last Updater Setting Program Execution Error (S7).")


    except Exception as e:
        logging.error(f"Failed to execute ERROR handling: {e}")

    finally:
        if conn:
            conn.close()
        # 4. プログラムの終了
        sys.exit(1)
