
from datetime import datetime
import os
import sys
import time
import glob
import shutil
import sqlite3
import logging
import requests
import subprocess


from pypdf import PdfWriter, PdfReader
import pikepdf
from pikepdf import Array, Stream

from ERROR import ERROR_main

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
        #print(result)

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


# ERROR (2DPDFエラー発生用) ==================================================
# 2DPDFの生成でエラーが出た場合は、
# 3DPDFをマージ => 3DPDFのみをアップロード => エラー処理 の流れで対応する

# (最後に実施)xmlファイルの数 = 3DPDFの数 かどうかを確認
def file_num_check(job_db, job_id, xml_path, pdf_3d_path, error_msg):

    max_num      = 30  # ファイルの数を確認する最大回数
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
                break
            if retry_count < max_num:
                time.sleep(2)
                retry_count += 1
            else:  # 30回試してもダメだった場合
                new_error_msg = f"[ERROR Hanndling Failed] xml and 3DPDF file count mismatch. \n[Original Error] {error_msg}"
                ERROR_main(job_db, job_id, new_error_msg, g_cadno, g_user_id)

        except Exception as e:
            new_error_msg = f"[ERROR Hanndling Failed] {e}\n[Original Error] {error_msg}"
            ERROR_main(job_db, job_id, new_error_msg, g_cadno, g_user_id)

# TEMPフォルダ内の移動・Innovatorアップロード用ファイルの作成
def get_pdf_names(job_db, job_id, cat_temp):

    # --- マージした2DPDFのファイル名を作成する ---
    # CAT_TEMP フォルダ内の *DRS* ファイルを取得
    drs_file = glob.glob(os.path.join(cat_temp, "*DRS*"))

    if not drs_file:
        error_msg = "CATIA file with 'DRS' not Found. Please upload the DRS01 native file.(E2)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        return

    drs_file_path   = os.path.basename(drs_file[0])   # 例）~/CAT_TEMP/C11-02713_DRS01_--A.CATProduct
    drs_filename    = os.path.basename(drs_file_path) # 例）C11-02713_DRS01_--A.CATProduct
    pdf_base_name = os.path.splitext(drs_filename)[0] # 例) C11-02713_DRS01_--A
    pdf3_name  = f"{pdf_base_name}.pdf"

    return pdf3_name 

# 3DPDFのマージ
def make_3dpdfs(job_db, job_id, temp_pdf3_path, attached_pdf_name, inv_folder):

    # PDFの添付(pypdf)を実行
    # INPUT  -> 2DPDFが格納されているフォルダ：temp_pdf3_path
    # OUTPUT -> INVフォルダ (ファイル名 attatched_pdf_name )
    # print(glob.glob(os.path.join(temp_pdf3_path, "*.pdf")))

    input_3d_files = sorted(glob.glob(os.path.join(temp_pdf3_path, "*.pdf")), key=os.path.getmtime, reverse=True) #更新日時が新しい順でソート
    output_3d_file = os.path.join(inv_folder, attached_pdf_name)
    
    # 3DPDFの添付 ----------
    if not temp_pdf3_path:
        error_msg = "3DPDF file not Found.(E2)"
        # ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

    # STOCKしかない場合：添付するファイルがないので、コピーだけする
    elif len(input_3d_files) == 1:
        shutil.copy(input_3d_files[0], output_3d_file)

    else:
        # 2つ以上ある場合：
        latest_pdf_path = input_3d_files[0]   # [0] が最も新しい(ベース) = STOCK
        files_to_attach = input_3d_files[1:]  # [1:] が古い (添付対象)   = PA***

        # ベースとなる最新ファイルを PdfReader で開く
        
        reader = PdfReader(latest_pdf_path)
        
        # 新しい PdfWriter を作成し、ベースPDFのページをコピー
        merger = PdfWriter(clone_from=reader) # 3DPDFの工程注記が消えないようにする
        reader.close()

        # 残りのファイル (files_to_attach) を添付ファイルとして追加
        for file_path in files_to_attach:
            # ★ 添付ファイル名にはフルパスではなく「ファイル名」を使う
            file_name = os.path.basename(file_path)

            #logging.info(file_name)
            try:
                with open(file_path, 'rb') as f_attach:
                    logging.info(file_path)
                    file_data = f_attach.read()
                # PdfWriterオブジェクトに添付ファイルを追加
                merger.add_attachment(file_name, file_data)
                logging.info(f"Successfully attached: {file_name}")
            except Exception as e:
                logging.info(f"Warning: Failed to attach {file_name}. Error: {e}")

        # 7. 最終的なPDFファイル（ベース＋添付ファイル）を保存
        with open(output_3d_file, "wb") as f_out:
            merger.write(f_out)
        logging.info(f"3D Attachment process completed. Output file: {output_3d_file}")   


g_cadno = None
g_user_id = None

# 3DPDFマージ → 3DPDFだけアップロード(Con:OK) → エラーを吐く
def ERROR_main_3dup(db_path, job_id: str, error_msg: str, cadno, user_id, cn_path):

    global g_cadno
    global g_user_id

    g_cadno = cadno
    g_user_id = user_id

    # 仮の3DPDFが入ったフォルダのパス
    pdf_3d_path = os.path.join(cn_path, "3DPDF_TEMP")

    # xmlの数 = 3DPDFフォルダの中のファイルの数 を確認
    xml_path = os.path.join(cn_path, "XML", "xml")
    file_num_check(db_path, job_id, xml_path, pdf_3d_path, error_msg)

    # 3DPDFの名前を作る
    cat_temp = os.path.join(cn_path, "CAT_TEMP")
    pdf3_name = get_pdf_names(db_path, job_id, cat_temp)

    # 出力先のパスを作成
    inv_folder    = os.path.join(cn_path, "INV")
    os.makedirs(inv_folder, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    inv_outputfolder = os.path.join(inv_folder, timestamp)
    os.makedirs(inv_outputfolder, exist_ok=True)

    # マージ
    make_3dpdfs(db_path, job_id, pdf_3d_path, pdf3_name, inv_outputfolder)
    conn = None
    try:
        # 3DPDFのみのアップロード処理(ダミーの処理) ----------------------------

        ## CADドキュメント番号、社員番号, ファイル作成結果
        create_file_result = "OK"

        ## ファイルパス
        pdf_2d_path = r"C:\3DPDF\99_3DPDF_generate\________.txt"
        pdf_3d_path =  os.path.join(inv_outputfolder, pdf3_name)

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
                logging.error("3DPDF Upload Program Execution Error (E2).")
        except Exception as e: 
            error_msg = f"{e}(E2)"
            logging.error(f"Failed to execute 3DPDF Upload Program: {error_msg}")


        # 本当のエラー処理 ----------------------------

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


        # 3DPDFアップロードプログラムの呼び出し
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.returncode == 0: # 正常終了
                logging.info("3DPDF Upload Program Executed Successfully (ERROR).")

            else: # 異常終了
                logging.error("3DPDF Upload Program Execution Error (E2).")
        except Exception as e: 
            error_msg = f"{e}(E2)"
            logging.error(f"Failed to execute 3DPDF Upload Program: {error_msg}")

        # 最終更新者をAdminではなく、実行者本人にするプログラム
        # 本番環境
        url = rf"http://{UPLOAD_URL}/Aras_RD_CAD/LastUserSv?userid={user_id}&cadno={cadno}"

        response = requests.get(url)
        if response.status_code == 200:
            logging.info("Last Updater Setting Program Executed Successfully (ERROR).")
        else:
            logging.info(f"Last Updater Setting Program Execution Error.")


    except Exception as e:
        logging.error(f"Failed to execute ERROR handling: {e}")

    finally:
        if conn:
            conn.close()
        # 4. プログラムの終了
        sys.exit(1)