"""
File vaultを通じてCATIAファイルをダウンロードする。
3DPDFなどを入れておくフォルダを公開先・CNに基づいて作成する。
"""

import re
import os
import logging
import requests
from ERROR import ERROR_main

from dotenv import load_dotenv
load_dotenv()
VAULT_URL= os.getenv("VAULT_URL") 


# フォルダパス関連処理 ------------------------------------------

def get_cn_relative_path(cn, base_path):
    # 正規表現: アルファベット1文字 + 数字2桁 + '-' + 数字5桁
    # name_pattern = re.compile(r"^([A-Z])(\d{2})-(\d{5})")
    name_pattern = re.compile(r"^([A-Z])(\d{2})-([A-Z0-9]{5})")
    match = name_pattern.match(cn.strip())

    # マッチしない場合は Others へ
    if not match:
        cn_path = os.path.join(base_path, "Others", cn)
        return cn_path

    prefix = match.group(1)      # F, A, C
    code_str = match.group(2)    # 01, 11, 41...
    code_int = int(code_str)     # 数値として比較するために変換 (重要！)
    serial = match.group(3)      # 02146(下5桁)

    category_path = ""

    # 大分類
    if prefix == "F":
        top = "F_Finish"
        # Fの場合はそのまま2桁を使うか、00/01で分ける
        # 小分類
        if code_str in ["00", "01"]:
            sub = code_str
        else:
            sub = code_str
        
        # 例：F01-02146の場合
        # category_path: F_Finish/01
        category_path = os.path.join(top, sub)

        # 下5桁の分類
        major_folder = serial[0:2] + "XXX"
        minor_folder = serial[0:3] + "XX"

        # 例：F01-02146の場合
        # cn_path = F_Finish/01/02XXX/021XX/F01-02146
        cn_path = os.path.join(base_path, category_path, major_folder, minor_folder, cn)

        return cn_path

    elif prefix == "A":
        top = "A_Assembly"
        if code_str in ["41", "42", "43", "44", "48", "49"]:
            sub = code_str
        else:
            sub = "Unknown_Assembly"
        category_path = os.path.join(top, sub)

        # 下5桁の分類
        major_folder = serial[0:2] + "XXX"
        minor_folder = serial[0:3] + "XX"

        # 例：A41-02146の場合
        # cn_path = A_Assembly/41/02XXX/021XX/A41-02146
        cn_path = os.path.join(base_path, category_path, major_folder, minor_folder, cn)

        return cn_path

    elif prefix == "C":
        top = "C_Component"
        if (11 <= code_int <= 19) or (51 <= code_int <= 59):
            sub = "11-19_51-59(BODY)"
        elif 21 <= code_int <= 29:
            sub = "21-29(RACE)"
        elif 31 <= code_int <= 39:
            sub = "31-39(BALL)"
        elif 61 <= code_int <= 69:
            sub = "61-69(SLEEVE)"
        elif code_int == 81 or code_int == 95:
            sub = "81(STUD)_95(MECHA)"
        elif 82 <= code_int <= 99:
            sub = "82-99(OTHERS)"
        else:
            sub = "Unknown_Parts"
        
        category_path = os.path.join(top, sub, code_str)
        
        # 下5桁の分類
        major_folder = serial[0:2] + "XXX"
        minor_folder = serial[0:3] + "XX"

        cn_path = os.path.join(base_path, category_path, major_folder, minor_folder, cn)

        return cn_path
    
    else:
        # F, A, C 以外
        cn_path = os.path.join(base_path, "Others", cn)
        return cn_path


def make_dl_path(job_db, job_id, list_1, cn):
    cn_mid = list_1.get('cn_mid')
    temp_folder = "CAT_TEMP"
    
    # 公開先
    if cn_mid == '3BD346BA17014C76BC637A3179702F52': # RD_ALL のとき
        base_path   = r"C:\3DPDF\20_3DPDF_result\RD_ALL"
        cn_path     = get_cn_relative_path(cn, base_path)
        folder_path = os.path.join(cn_path, temp_folder)
        os.makedirs(folder_path, exist_ok=True) 
        return folder_path, cn_path

    elif cn_mid == 'C56AE2BCB9C44EB7BC8A8172BB632B26': # KZW_ALL
        base_path   = r"C:\3DPDF\20_3DPDF_result\KZW_ALL"
        cn_path     = get_cn_relative_path(cn, base_path)
        folder_path = os.path.join(cn_path, temp_folder)
        os.makedirs(folder_path, exist_ok=True) 
        return folder_path, cn_path
    elif cn_mid == '47985AFE883F45A59C7C6B9CCBF083FF': #KZW_ERI
        base_path   = r"C:\3DPDF\20_3DPDF_result\KZW_ERI"
        cn_path     = get_cn_relative_path(cn, base_path)
        folder_path = os.path.join(cn_path, temp_folder)
        os.makedirs(folder_path, exist_ok=True) 
        return folder_path, cn_path
    else: # それ以外: KZW_ALL/KZW_ERI/RD_ALL 以外の公開先なので、もし存在する場合は上記if文に設定する必要がある
        error_msg = "Unexpected Managed_by_id. Please contact to the administrators.(S2)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

# -------------------------------------------------------------

g_cadno = None
g_user_id = None

def S2_main(job_db, job_id, list_1, list_2, cn, cadno, user_id):
    failed_files = [] # ダウンロードに失敗したファイルのリスト   

    # グローバル変数を設定
    global g_cadno
    global g_user_id

    g_cadno = cadno
    g_user_id = user_id

    if list_2 == None:
        logging.error("List 2 is none")

    # ループ処理の初回：もしフォルダ内にCATIAファイルがあれば削除する
    is_first_run = True

    for row in list_2:

        cat_name = row[0]
        id_link  = row[1]
        dl_id   = f"{id_link[0]}/{id_link[1:3]}/{id_link[3:]}"
        
        ## TODO 本番
        dl_url = f"http://{VAULT_URL}/RD_Vault/{dl_id}/{cat_name}"

        # CATファイルのDL先  C:(公開先)\CAT_TEMP
        cn_path = None
        dl_path = None

        dl_path, cn_path = make_dl_path(job_db, job_id, list_1, cn)

        if is_first_run:
            if os.path.exists(dl_path):
                logging.info(f"Cleaning directory: {dl_path}")
                for filename in os.listdir(dl_path):
                    file_path = os.path.join(dl_path, filename)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logging.warning(f"Failed to delete {filename}: {e}")
            # フラグを折る
            is_first_run = False

        destination_path = os.path.join(dl_path, cat_name) # ダウンロード先のパス
        # bitsadminのために、パス区切り文字をバックスラッシュに統一する
        destination_path = destination_path.replace('/', '\\')

        logging.info(f"Downloading: {cat_name}")
        try:
            response = requests.get(dl_url, stream=True, timeout=60)
            response.raise_for_status()
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        except requests.exceptions.ConnectionError:
            error_msg = f"Failed to Download CATIA File. Connection Error.(S2)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
            return
        except requests.exceptions.HTTPError as e:
            error_msg = f"Failed to Download CATIA File. HTTP {e.response.status_code}.(S2)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
    if failed_files:
        logging.info(f"Failed to Download CATIA Files: {len(failed_files)}/ {len(list_2)}")
        # error_details = "\n".join([f"- {item}" for item in failed_files])
        # error_msg= f"{header}\n\n▼Failed Files\n{error_details}"
        error_msg = f"Failed to Download CATIA Files.(S2)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
    return cn_path