"""
Adobeで2DPDFの作成
"""
import os
import glob
import time
import shutil
import logging
import subprocess

from ERROR import ERROR_main
from ERROR_3DPDF_up import ERROR_main_3dup

# エラー処理用関数 ====================================
# Adobeプロセス強制終了用関数 
def kill_acrobat_process():
    """
    実行中のAcrobat Readerのプロセスを強制終了する。
    Adobeが開いたままの状態では、新規の3DPDFが開かないことがあるため。
    """
    # Acrobat Pro と Reader の両方をターゲット
    process_names = "Acrobat.exe"
    
    try:
        # /F: 強制終了, /IM: イメージ名（プロセス名）
        # taskkillがエラーコード128を返すことがあるが、プロセスがない場合は正常として扱う
        result = subprocess.run(
            ["taskkill", "/F", "/IM", process_names],
            check=False, # エラーコードをチェックしない
            capture_output=True,
            text=True
        )
        if result.returncode == 0: # 正常終了
            logging.info(f"Killed {process_names} process.")
        elif process_names in result.stdout:
            # 既にプロセスが存在しない場合
            pass
        #else:
            #error_msg = "Failed to kill Acrobat.(S5)"
            #ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

    except FileNotFoundError:
        # taskkillコマンドが見つからない（非Windows環境など）
        logging.info("Error: taskkill command not found. Acrobat process cannot be killed.")
    except Exception as e:
        logging.info(f"Error while trying to kill {process_names}: {e}")

# ====================================================


def ready(job_db, job_id, pdf_3d_path):
    max_num      = 30  # ファイルの数を確認する最大回数
    retry_count  = 0

    while retry_count <= max_num:
        try:
            pdf_3d_files = glob.glob(os.path.join(pdf_3d_path, "*.pdf"))
            logging.info("Waiting for the first 3DPDF...")

            # ファイルが1つ以上あれば break
            if len(pdf_3d_files) > 0:
                logging.info(f"Ready to start generating 2DPDF.")
                break
                
            if retry_count < max_num:
                time.sleep(2)
                retry_count += 1
            else:  # 30回試してもダメだった場合
                error_msg = "3DPDF file not found in 3DPDF_TEMP.(S5)"
                ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
                
        except Exception as e:
            error_msg = f"{e}(S5, ready)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

def delete_temps(job_db, job_id, temp_path):
    # found_items = 0
    delete_path = os.path.join(temp_path, '*')
    for item_path in glob.glob(delete_path):

        if os.path.isfile(item_path):
            try:
                # 削除
                os.remove(item_path)

                # found_items += 1
            except OSError as e:
                # (例: 権限がない、ファイルが使用中など)
                error_msg= f"Failed to Delete {item_path} {e}"
                ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        else:
            # *_TEMP という名前の「フォルダ」は無視されます
            pass


# C:\Adobe_logging.info\done.pdfを削除 -> 3DPDFを開く
# 上記の繰り返し
def create_2dpdf(job_db, job_id, xml_path, pdf_3d_path):
    # 1つのPDFを開いてから 'done.pdf' ができるまでの最大待機時間:90秒
    PROCESS_TIMEOUT_SECONDS = 90
    MAX_OPEN_RETRIES = 2 # done.pdf確認プロセスの最大実行回数
    
    # 2DPDF生成完了トリガー
    # ここにdone.pdfが生成されたら1つの3DPDFに対する2DPDFが生成完了したことになる。
    done_path = r"C:\3DPDF\14_Adobe_print\done.pdf"

    # --- 1. XMLの数を取得 ---
    # xmlファイルの数が0個ならエラーを吐く
    try:
        xml_files = glob.glob(os.path.join(xml_path, "*.xml"))
        xml_count = len(xml_files)
        if xml_count == 0:
            error_msg = "XML Files NOT Found.(S5)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
    except Exception as e:
        error_msg = f"{e}(S5, checking XML count)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
    
    # --- 2. PA***のリストを作成 ---
    # pdfを開く際に利用する
    limit_i = xml_count - 1
    sheet_names = []
    for i in range(1, limit_i + 1):
        sheet_names.append(f"PA{i:02}0")

    sheet_names.append("STOCK") # 最後の1つは "STOCK"

    logging.info(f"Sheets to process: {sheet_names}")

    # Adobe Acrobatを開く: SessionMoniterによって解決したのでコメントアウト
    acrobat_path = r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe"
    subprocess.Popen(acrobat_path)

    # --- 3. ファイルを叩く ---
    for sheet in sheet_names:

        # done.pdfがあれば消す
        max_retries = 2 # 試行回数
        
        for i in range(max_retries):
            try:
                if os.path.exists(done_path):
                    os.remove(done_path)
                
                # 削除成功、またはファイルが無かった場合はループを抜ける
                break 

            except OSError as e:
                # エラーが発生した場合（ファイルロックなど）
                if i < max_retries - 1:
                    # まだリトライ回数が残っている場合
                    time.sleep(1) # 1秒待機して次のループへ
                    continue
                else:
                    # 最後の1回も失敗した場合 -> エラー確定
                    error_msg = f"Failed to delete done.pdf after {max_retries} attempts. {e}(S5)"
                    ERROR_main_3dup(job_db, job_id, error_msg, g_cadno, g_user_id, g_cn_path)

        # {sheet}(例：PA010)を含むファイルを3DPDF_TEMPから探す
        signal_3dpdf_path = os.path.join(pdf_3d_path, f"*{sheet}*")
            
        # タイムアウト時間 = 90
        current_timeout = PROCESS_TIMEOUT_SECONDS

        # --- A. 3DPDFの検索とAcrobatの起動 [ループ A] ---
        count_seach_3dpdf = 0
        max_search        = 60
        target_3dpdf_path = None
        
        # {sheet}を含む3DPDFファイルを検索し、Acrobatで開く
        while True:
            try:
                # {sheet}を含むファイルを3DPDF_TEMPから探す
                logging.info(f"{sheet}: Seaching for 3DPDF...")
                target_3dpdf = glob.iglob(signal_3dpdf_path)
                target_3dpdf_path = next((item for item in target_3dpdf if os.path.isfile(item)), None)
                
                if target_3dpdf_path:
                    max_open_adobe = 3   # Adobeを再度開く最大回数
                    open_success = False # 成功できたかどうか
                    
                    for i in range(max_open_adobe): # Adobeを開きなおす[ループC]
                        try:
                            logging.info("Opening Acrobat...")
                            os.startfile(target_3dpdf_path)
                            open_success = True
                            break # [ループC] を抜ける
                        except Exception as e:
                            logging.error(f"Failed to open Acrobat: {e}")
                            # 最後の試行でなければ、キルしてリトライ
                            if i < max_open_adobe - 1:
                                kill_acrobat_process()
                                time.sleep(3) # プロセスが完全に消えるのを少し待つ
                            else:
                                # 最終回でもダメだった場合、例外を再送出して外側のexceptブロックへ
                                raise e
                    if open_success:
                        break # [ループ A] を抜ける
                else:
                    time.sleep(2)
                    count_seach_3dpdf += 1 

                    # 3DPDFが見つからないエラー
                    if count_seach_3dpdf == max_search: # 30回試してもダメだった場合
                        error_msg = f"3DPDF NOT FOUND after 120 sec wait.(S5)"
                        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
                        break # [ループA] を抜ける
            
            except Exception as e:
                error_msg = f"{e}(S5)"
                ERROR_main_3dup(job_db, job_id, error_msg, g_cadno, g_user_id, g_cn_path)
            
        # --- B. done.pdf の生成を待機 [ループB] ---
        count_seach_done = 0 # done.pdfを探す回数カウント

        while True:
            # done.pdf が追加されたら成功
            if os.path.exists(done_path):
                logging.info("Go to the next sheet.")

                time.sleep(2)
                # kill_acrobat_process()
                break # [ループB] を抜ける
            else:
                time.sleep(3) # 3秒ごとに確認
                count_seach_done += 1

                if count_seach_done == max_search: # 30回試してもダメだった場合
                    error_msg = f"done.pdf NOT FOUND after 90sec wait.(S5)"

                    # C:\TEMP の中身を消す(念のため)
                    temp_path = r"C:\3DPDF\10_TEMP"
                    delete_temps(job_db, job_id, temp_path)

                    ERROR_main_3dup(job_db, job_id, error_msg, g_cadno, g_user_id, g_cn_path)
                    break # [ループB] を抜ける


g_cadno = None
g_user_id = None
g_cn_path = None
def S5_main(job_db, job_id, cn_path, cadno, user_id):

    # グローバル変数にcadnoをセット
    global g_cadno
    global g_user_id
    global g_cn_path

    g_cadno = cadno
    g_user_id = user_id
    g_cn_path = cn_path
    
    PDF_3D_PATH = os.path.join(cn_path, "3DPDF_TEMP")
    XML_PATH    = os.path.join(cn_path, "XML", "xml")

    ready(job_db, job_id, PDF_3D_PATH)

    # C:\TEMP の中身を消す(念のため)
    temp_path = r"C:\3DPDF\10_TEMP"
    delete_temps(job_db, job_id, temp_path)

    create_2dpdf(job_db, job_id, XML_PATH, PDF_3D_PATH)

    time.sleep(2)
    kill_acrobat_process()

    # Tempフォルダ内のPDFの数を確認
    # 0個ならエラーを吐く
    try:
        temp_pdf_files = glob.glob(os.path.join(temp_path, "*.pdf"))
        temp_pdf_count = len(temp_pdf_files)
        if temp_pdf_count == 0:
            error_msg = "2DPDF Files NOT Found in '10_TEMP'.(S5)"
            ERROR_main_3dup(job_db, job_id, error_msg, g_cadno, g_user_id, g_cn_path)
    except Exception as e:
        error_msg = f"{e}(S5, checking 2DPDF count)"
        ERROR_main_3dup(job_db, job_id, error_msg, g_cadno, g_user_id, g_cn_path)

    # --- 10_TEMP内の2DPDFをCNの2DPDF_TEMPに移動 ---
    # (競合防止のため、S5の最後で即座に移動する)
    temp_pdf2_path = os.path.join(cn_path, "2DPDF_TEMP")

    if os.path.exists(temp_pdf2_path):  # 既存フォルダがあれば削除
        shutil.rmtree(temp_pdf2_path)
        time.sleep(2)

    os.makedirs(temp_pdf2_path, exist_ok=True)

    temp_files = glob.glob(os.path.join(temp_path, "*.*"))
    if not temp_files:
        time.sleep(5)
        temp_files = glob.glob(os.path.join(temp_path, "*.*"))
        if not temp_files:
            error_msg = "Failed to move 2DPDF. C:\\3DPDF\\10_TEMP is Empty(S5)"
            ERROR_main_3dup(job_db, job_id, error_msg, g_cadno, g_user_id, g_cn_path)
    else:
        for f in temp_files:
            if os.path.isfile(f):
                shutil.move(f, os.path.join(temp_pdf2_path, os.path.basename(f)))

    # --- 10_TEMPに残ったファイルを削除 ---
    remaining_files = glob.glob(os.path.join(temp_path, "*.*"))
    for f in remaining_files:
        if os.path.isfile(f):
            os.remove(f)