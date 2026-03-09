"""
MAIN PROGRAM FOR 3DPDF GENERATION
AND FILE UPLOAD TO INNOVATOR
"""
import os
import sys
import time
import glob
import psutil
import shutil
import sqlite3
import logging
import requests
import subprocess
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
UPLOAD_URL = os.getenv("UPLOAD_URL")

# 各ファイルから、使いたい関数をインポートする
from job_db.P1_get_CATIApass import get_info
from job_db.P2_register_job  import create_and_insert_job
from job_db.P3_logger_config import setup_logger
from S1_query          import S1_main
from S2_get_native_cat import S2_main
from S3_create_xml     import S3_main
from S3_2_create_xml   import S3_2_main
from S4_create_bat     import S4_main
from S5_2DPDF_create   import S5_main
from S6_2DPDF_merge    import S6_main
from S7_give_info      import S7_main
from ERROR             import ERROR_main

# TODO DBパスの設定
# 本番
DB_PATH = r"C:\3DPDF\99_3DPDF_generate\job.db"


# 次のプロセスが空いているかチェック
def check_next_process(db_path, job_id, next_key, current_key):
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        
        # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
        # これにより「読み込み」と「書き込み」が同時にできるようになります
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()

        # 「次のプロセス」かつ「コンディションがNULL」のものを出力
        # コンディションがNULL = 実行中(ErrorやCancelではない。)
        sql1 = """
            SELECT *
            FROM job
            WHERE job.status = ? AND condition IS NULL;
        """

        # 今のプロセス(Waiting XXX)について、自分が最新かどうかを確認
        # 自分が「ORDER BY date ASC(古い順)」の一番上 = 一番古く並んでいる。
        sql2 = """
            SELECT job_id 
            FROM job 
            WHERE status = ? AND condition IS NULL 
            ORDER BY date ASC 
            LIMIT 1
        """
        
        cursor.execute(sql1, (next_key,))
        result1 = cursor.fetchone() # 次のプロセスの空き確認
        
        cursor.execute(sql2, (current_key,))
        result2 = cursor.fetchone() # 現行と同じプロセスの確認

        #logging.info(result1, result2[0])

        flag = result1 is None and (result2[0] == job_id)

        if flag:
            status = (next_key, job_id)
            cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
            logging.info(" >> Checking Other Process... OK")

        else:

            sql3 = """
                UPDATE job
                SET condition = 'Failed'
                WHERE job_id = (
                    SELECT job_id
                    FROM job
                    WHERE status = ?
                        AND condition IS NULL
                        AND date <= datetime('now', '-15 minutes')
                    ORDER BY date ASC
                    LIMIT 1
                );
            """

            # もし"Processing 2D/3DPDF"が15分以上実行されている場合、
            # そのプロセスを"Failed"に更新する
            # 得体の知れないエラーにより、ジョブがFailed もしくは Cancel されずに終了した場合の対策
            cursor.execute(sql3, (next_key,))
            conn.commit()

            # flagがFalseだった場合、最大300秒間リトライする
            for i in range(100):  # 100回ループ
                
                dots = "." * ((i % 3) + 1) # 点の数を3個単位でループ
                logging.info(f"\r >> Checking Other Process {dots:<3}")

                time.sleep(3)  # 3秒待機

                # 再度SQL実行
                cursor.execute(sql1, (next_key,))
                result1 = cursor.fetchone() # 次のプロセスの空き確認
                
                cursor.execute(sql2, (current_key,))
                result2 = cursor.fetchone() # 現行と同じプロセスの確認

                #logging.info(result1, result2[0])
                flag = result1 is None and (result2[0] == job_id)

                if flag:
                    status = (next_key, job_id)
                    cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
                    logging.info("\r >> Checking Other Process ... OK")
                    break  # 目的を達成したのでループを抜ける
            
            else:
                logging.info("\r >> Checking Other Process ... ERROR")
                error_msg = "[JOB TIMEOUT] Resource currently occupied by another user. Process aborted after 100 times of retries"
                ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)
    
    except Exception as e:
        error_msg = f'{e}'
        ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)
        
    finally:
        conn.commit()
        conn.close()

def close_adobe_if_open():
    """
    実行中のAdobeプロセスを探して終了させます。
    見つからなければ何もしません。
    """

    target_processes = ["Acrobat.exe", "AcroRd32.exe"]     
    logging.info("Checking whether Adobe Acrobat is open...")
    
    found_process = None
    try:
        # 現在実行中の全プロセスをイテレート
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] in target_processes:
                found_process = proc
                break

        if found_process:
            logging.info(f"Closing Adobe Arobat...")
            
            # 1. 安全な終了 (terminate) を試みる
            found_process.terminate()
            
            # 2. 終了するまで少し待つ (最大5秒)
            try:
                found_process.wait(timeout=5)
                logging.info("Adobe Closed")
            except psutil.TimeoutExpired:
                # 3. 5秒経っても終了しない場合、強制終了 (kill)
                logging.info("Killing Adobe...")
                found_process.kill()
                found_process.wait(timeout=3) # 強制終了の完了を待つ
                logging.info("Adobe Closed")
                
        else:
            logging.info("Adobe was not opened")

    except psutil.NoSuchProcess:
        # waitの直前にプロセスが（手動などで）終了した場合
        logging.info("Adobe have already cloed.")
    except psutil.AccessDenied:
        # 管理者権限がないと終了できない場合
        logging.error("There is no Access to Close Adobe.")
    except Exception as e:
        logging.error(f"Unexpected Error Occured: {e}")


def cancel_process(db_path, job_id):
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        
        # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
        # これにより「読み込み」と「書き込み」が同時にできるようになります
        conn.execute('PRAGMA journal_mode=WAL;')

        cursor = conn.cursor()


        # Conditionを 'Canceled' に設定
        condition_data = ('Canceled', job_id)
        cursor.execute('UPDATE job SET condition = ? WHERE job_id = ?', condition_data)

        conn.commit()

    except Exception as e:
        # エラー報告中にさらにエラーが起きた場合 (例: DBがロックされている)
        logging.error(f"Failed to Change Condition: {e}")
        
    finally:
        if conn:
            conn.close()

    # 3DPDFアップロードプログラムによって、Innovator 3DPDF生成状態を"ERROR"にする    
    try:
        ## ファイル作成結果
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

        # 4. 3DPDFアップロードプログラムの呼び出し(仮)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.returncode == 0: # 正常終了
                logging.info("3DPDF Upload Program Executed Successfully (Canceled).")
            else: # 異常終了
                error_msg = f"3DPDF Upload Program Execution Error (S7)."
                ERROR_main(db_path, job_id, error_msg, cadno, user_id)

        except Exception as e: 
            error_msg = f"{e}(S7)"
            ERROR_main(db_path, job_id, error_msg, cadno, user_id)

    except Exception as e:
        logging.error(f"Failed to execute ERROR handling: {e}")

    finally:
        # 4. プログラムの終了
        sys.exit(1)


    logging.info("Cancel Compleated")


# (最後に実施)xmlファイルの数 = 3DPDFの数 かどうかを確認
def final_check(job_db, job_id, cn_path):

    xml_path = os.path.join(cn_path, "XML", "xml")
    pdf_3d_path = os.path.join(cn_path, "3DPDF_TEMP")

    max_num      = 180  # ファイルの数を確認する最大回数
    retry_count  = 0
    xml_count    = 0
    pdf_3d_count = 0

    pdf_3d_files = []

    while retry_count <= max_num:
        try:
            xml_files    = glob.glob(os.path.join(xml_path, "*.xml"))
            pdf_3d_files = glob.glob(os.path.join(pdf_3d_path, "*.pdf"))

            xml_count    = len(xml_files)
            pdf_3d_count = len(pdf_3d_files)

            if xml_count == pdf_3d_count:
                logging.info(f"Final Check: The Number of xml files and 3DPDF is match. XML Count: {xml_count}, 3DPDF Count: {pdf_3d_count}")
                break
            if retry_count < max_num:
                time.sleep(2)
                retry_count += 1
            else:  # 180回試してもダメだった場合
                error_msg = "The Number of xml files and 3DPDF is not match.(Main)"
                ERROR_main(job_db, job_id, error_msg, cadno, user_id)

        except Exception as e:
            error_msg = f"{e}(S5)"
            ERROR_main(job_db, job_id, error_msg, cadno, user_id)


cadno = None # 空の変数を作る
user_id = None # 空の変数を作る
def main_process():
    global cadno
    global user_id  
    
    job_id = None
    try:
        # Prepare for the main program
        # P1. P1_get_CATIApass.py からcn値を取得

        cn, user_id, cadno, ver = get_info()

        # ログ作成
        logger, logger_path = setup_logger(cadno)

        logging.info("Starting the Progam ------")
        logging.info(f"CN: {cn}")
        # P2. P2_register_job の関数を呼び出し、job_idを受け取る
        job_id = create_and_insert_job(DB_PATH, user_id, cn)

        if "DRS" not in cadno:
            error_msg = "CAD Document number is not include DRS. Exiting the Program."
            logging.error(error_msg)
            ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)
            
            return None

        # Innovator> 3DPDF生成状態をRUNNINGに変更するプログラム
        # 本番環境
        url = f"http://{UPLOAD_URL}/Aras_RD_CAD/PdfStateSv?userid={user_id}&cadno={cadno}"

        # TODO
        try:
            response = requests.get(url)
            if response.status_code == 200:
                logging.info("Innovator 3DPDF State: 'RUNNING'")
            else:
                error_msg = f"Last Updater Setting Program Execution Error (main)."
                ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)
        except Exception as e:
            error_msg = f"{e}"
            ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)

        if job_id:
            # job_idが無事に作成・jobDBにも接続完了
            # メインの処理に入る
            
            # S1. S1_query.py の関数に job_id を渡して呼び出す
            list_1, list_2, list_3_1, list_3_2, list_3_3, list_4 = S1_main(DB_PATH, job_id, cn, user_id, cadno)
            
            # S2. S2_get_native_cat.py に job_id, list_2を渡して呼び出す
            cn_path = S2_main(DB_PATH, job_id, list_1, list_2, cn, cadno, user_id)

            # S3. S3_create_xml.pyに job_id, list_3, 4を渡して呼び出す
            if ver == 'v1.30':
                template_list = S3_main(DB_PATH, job_id, list_3_1, list_3_2, list_3_3, list_4, cn, cn_path, cadno, user_id)
            else:
                template_list = S3_2_main(DB_PATH, job_id, list_3_1, list_3_2, list_3_3, list_4, cn, cn_path, cadno, user_id)

            # S4. S4_create_bat.py
            bat_path = S4_main(cn, cn_path, DB_PATH, job_id, list_2, list_3_2,  list_3_3, cadno, user_id, ver, template_list) # コメントアウトで時短

            # 3DPDFジョブ(1アカウントのみ) --------------------------------------------------------------
            # 3DPDFのジョブがあるかを確認
            next_key = "Processing 3DPDF"
            check_next_process(DB_PATH, job_id, next_key, "Waiting for 3DPDF")

            target_path = r"C:\3DPDF\15_SmartExchange\Start_SmartExchange.bat" # コピー先のパス
            
            # コピー先のファイルの中身を消す
            with open(target_path, 'w', encoding='cp932') as f:
                pass
            

            shutil.copyfile(bat_path, target_path)

            # タスクスケジューラーを呼び出す
            trigger_args = [
                "schtasks",
                "/run",
                "/tn",
                "exec_SmartExchange_batch"  # 例: "RunSmartExchange"
            ]

            #subprocess.run(trigger_args, check=True, shell=True)
            subprocess.run(trigger_args, stdout=subprocess.DEVNULL, check=True, shell=True)

            logging.info("3DPDF Creation Started...")
            final_check(DB_PATH, job_id, cn_path) # 3DPDF生成とxmlの数が合っているかの最終確認
            logging.info("3DPDF Creation Completed!!")

            # -----------------------------------------------------------------------------------------

            # 2DPDFジョブ(1アカウントのみ)　--------------------------------------------------------------
            
            # DB更新
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
        
            # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
            # これにより「読み込み」と「書き込み」が同時にできるようになります
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            status = ('Waiting for 2DPDF', job_id)

            try:
                cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
                conn.commit()
                logging.info("[!]  Updated Job Condition -> Waiting for 2DPDF")
            except Exception as e:
                error_msg = f"{e}"
                ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)
                return None 
            finally:
                conn.close()

            # 2DPDFジョブチェック
            next_key = "Processing 2DPDF"
            check_next_process(DB_PATH, job_id, next_key, "Waiting for 2DPDF")

            # S5_2DPDF_create.bat : 2DPDF生成プログラム
            # TODO
            S5_main(DB_PATH, job_id, cn_path, cadno, user_id)
            # -----------------------------------------------------------------------------------------

            # S6_2DPDF_merge.bat : 2DPDFのマージプログラム
            pdf2_name, pdf3_name, inv_folder = S6_main(DB_PATH, job_id, cn_path, cadno, user_id, list_3_2)

            # S7_give_info.py    : アップロードプログラムを呼び出す
            S7_main(DB_PATH, job_id, pdf2_name, pdf3_name, inv_folder, user_id, cadno, cn_path)

        else:
            logging.error("Failed to Create the JOB. Program Filed.")
            

        logging.info("Process Completed ------")
        logging.shutdown()

        # ログファイルのコピー
        # C:\LOG -> {cn_path}\LOG へコピー
        dest_dir = os.path.join(cn_path, "LOG")
        os.makedirs(dest_dir, exist_ok=True)
            
        # コピー実行
        shutil.copy2(logger_path, dest_dir)
            

    except KeyboardInterrupt:
        logging.info("Detected [Ctrl + C]")
        logging.info("Canceling the Process...")

        close_adobe_if_open()
        cancel_process(DB_PATH, job_id)


    except Exception as e:

        logging.error("Unexpected Error Emerged !!")
        
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
        
            # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
            # これにより「読み込み」と「書き込み」が同時にできるようになります
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()

            # 1. Conditionを 'Failed' に設定
            condition_data = ('Failed', job_id)
            cursor.execute('UPDATE job SET condition = ? WHERE job_id = ?', condition_data)

            # 2. エラーメッセージを記録
            error_data = (f"{e}", job_id) # str()で囲んで安全にする
            cursor.execute('UPDATE job SET error = ? WHERE job_id = ?', error_data)

            conn.commit()

        except Exception as db_e:
            # エラー報告中にさらにエラーが起きた場合 (例: DBがロックされている)
            logging.error(f"Failed to Report ERROR: {db_e}")
            #logging.info(f"Original Error Message: {error_msg}")
            
        finally:
            if conn:
                conn.close()

        # プログラムを終了
        error_msg = f"ERROR: {e}"
        ERROR_main(DB_PATH, job_id, error_msg, cadno, user_id)


# --- プログラムの実行開始点 ---
if __name__ == "__main__":
    main_process()