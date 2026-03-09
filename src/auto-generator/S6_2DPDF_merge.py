"""
1. C:¥TEMPにある2DPDFをCNのフォルダに格納
2. マージする
3. Innovatorにアップロードするフォルダにアップロードする図面を格納する
"""

from datetime import datetime
import os
import time
import glob
import shutil
import sqlite3
import logging
import requests
import subprocess

from pypdf import PdfWriter, PdfReader
from ERROR import ERROR_main

# 環境変数
from dotenv import load_dotenv
load_dotenv()
UPLOAD_URL = os.getenv("UPLOAD_URL") 


# ジョブDBに "Merging 2DPDF(s)"と送る
def send_condition(db_path, job_id):
    conn = sqlite3.connect(db_path, timeout=30.0)
        
    # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
    # これにより「読み込み」と「書き込み」が同時にできるようになります
    conn.execute('PRAGMA journal_mode=WAL;')
    
    cursor = conn.cursor()
    status = ('Merging 2DPDF(s)', job_id)

    try:
        cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
        conn.commit()
        logging.info("[!]  Updated Job Condition -> Merging 2DPDF(s)")
    except Exception as e:
        error_msg = f"{e}(S6)"
        ERROR_main(db_path, job_id, error_msg)
        return None 
    finally:
        conn.close()

#Innovatorアップロード用ファイルの作成
def get_pdf_names(cadno, list_3_2):

    approval_info = list_3_2[0]
    rev      = approval_info[7] 

    pdf2_name = f"{cadno}_{rev}_2D.pdf"       # 例) C11-02713_DRS01_--A_2D.pdf
    pdf3_name = f"{cadno}_{rev}.pdf"       # 例) C11-02713_DRS01_--A.pdf

    return pdf2_name, pdf3_name 

def make_2dpdfs(job_db, job_id, temp_pdf2_path, merged_pdf_name, inv_folder):

    # PDFのマージ(pypdf)を実行
    # INPUT  -> 2DPDFが格納されているフォルダ：temp_pdf2_path
    # OUTPUT -> INVフォルダ (ファイル名 merged_pdf_name )

    merger_2d = PdfWriter() #マージ用のPDFオブジェクト
    input_2d_files = sorted(glob.glob(os.path.join(temp_pdf2_path, "*.pdf")), key=os.path.getmtime) #更新日時が古い順でソート
    output_2d_file = os.path.join(inv_folder, merged_pdf_name)

    try:
        if not input_2d_files:
            error_msg = "Individual 2DPDFs are not Found.(S6)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        else:
            for filename in input_2d_files:
                reader = PdfReader(filename)
                merger_2d.append(reader)
                if len(merger_2d.pages) > 0:

                    # 2DPDFのマージ
                    with open(output_2d_file, "wb") as f_out_2D:
                        merger_2d.write(f_out_2D)

                else:
                    error_msg = "The 2DPDF_TEMP Directory is Empty.(S6)"
                    ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
            logging.info(f"2DPDF(s) Merge Completed. Output file: {output_2d_file}")

    except Exception as e:
        error_msg = f"{e}(S6:make_2dpdfs)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)



def make_3dpdfs(job_db, job_id, temp_pdf3_path, attached_pdf_name, inv_folder):

    # PDFの添付(pypdf)を実行
    # INPUT  -> 2DPDFが格納されているフォルダ：temp_pdf3_path
    # OUTPUT -> INVフォルダ (ファイル名 attatched_pdf_name )
    # print(glob.glob(os.path.join(temp_pdf3_path, "*.pdf")))

    input_3d_files = sorted(glob.glob(os.path.join(temp_pdf3_path, "*.pdf")), key=os.path.getmtime, reverse=True) #更新日時が新しい順でソート
    output_3d_file = os.path.join(inv_folder, attached_pdf_name)
    
    # 3DPDFの添付 ----------
    if not temp_pdf3_path:
        error_msg = "3DPDF file not Found.(S6)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

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


# 3DPDfだけ先にアップロードする
# エラーが出てもいったん無視
def upload_3dpdf_only(db_path, job_id, user_id, pdf3_name, inv_folder, cadno, cn_path):
    ## ファイル作成結果
    create_file_result = "OK"

    ## ファイルフルパス
    pdf_2d_path =  r"C:\3DPDF\99_3DPDF_generate\________.txt" # 実在するファイル
    pdf_3d_path =  os.path.join(inv_folder, pdf3_name)

    ## 3DPDFアップロードプログラムを呼び出す
    exe_path = r"C:\3DPDF\13_FileUploadProgram\ArasCadViewUpload_Rodend.exe"

    ## ログファイルパス
    log_path = os.path.join(cn_path, "LOG") + "\\"

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

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        # 3DPDF生成状態：RUNNNING に戻す
        # Innovator> 3DPDF生成状態をRUNNINGに変更するプログラム        
        url = f"http://{UPLOAD_URL}/Aras_RD_CAD/PdfStateSv?userid={user_id}&cadno={cadno}" # 本番環境

        try:
            response = requests.get(url)
            if response.status_code == 200:
                logging.info("Innovator 3DPDF State: 'RUNNING'")
            else:
                error_msg = f"Last Updater Setting Program Execution Error (S6)."
                ERROR_main(db_path, job_id, error_msg, cadno, user_id)
        except Exception as e:
            error_msg = f"{e}"
            ERROR_main(db_path, job_id, error_msg, cadno, user_id)
    
        if result.returncode == 0: # 正常終了
            logging.info("3DPDF Upload Program Executed Successfully.(OK)")
        else: # 異常終了
            logging.warning("3DPDF Upload Program Execution Error (S6).")

    except Exception as e: 
        error_msg = f"{e}(S6)"
        logging.error(error_msg)

g_cadno = None
g_user_id = None
def S6_main(job_db, job_id, cn_path, cadno, user_id, list_3_2):
    global g_cadno
    global g_user_id

    g_cadno = cadno
    g_user_id = user_id
        
    send_condition(job_db, job_id)

    pdf2_name, pdf3_name, inv_folder = None, None, None
    
    temp_pdf2_path = os.path.join(cn_path, "2DPDF_TEMP")
    temp_pdf3_path = os.path.join(cn_path, "3DPDF_TEMP")

    inv_folder    = os.path.join(cn_path, "INV")
    os.makedirs(inv_folder, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 図面出力用
    inv_outputfolder = os.path.join(inv_folder, timestamp)
    os.makedirs(inv_outputfolder, exist_ok=True)

    cat_temp      = os.path.join(cn_path, "CAT_TEMP")

    pdf2_name, pdf3_name = get_pdf_names(cadno, list_3_2)

    # 3DPDFのマージ
    make_3dpdfs(job_db, job_id, temp_pdf3_path, pdf3_name, inv_outputfolder)
    upload_3dpdf_only(job_db, job_id, user_id, pdf3_name, inv_outputfolder, cadno, cn_path)

    # 2DPDFのマージ
    make_2dpdfs(job_db, job_id, temp_pdf2_path, pdf2_name, inv_outputfolder)

    # CATIAフォルダの中身を消す
    shutil.rmtree(cat_temp)
    return pdf2_name, pdf3_name, inv_outputfolder