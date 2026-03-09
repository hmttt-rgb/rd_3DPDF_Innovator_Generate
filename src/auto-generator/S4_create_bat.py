"""
Smart Exchangeに渡すbatchファイルの作成
"""
from S1_query import g_user_id
import logging
import os
import shutil
import logging
import sqlite3
from ERROR             import ERROR_main

# ジョブDBに "Waiting for 3DPDF"と送る
def send_condition(db_path, job_id):
    conn = sqlite3.connect(db_path, timeout=30.0)
        
    # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
    # これにより「読み込み」と「書き込み」が同時にできるようになります
    conn.execute('PRAGMA journal_mode=WAL;')
    cursor = conn.cursor()
    status = ('Waiting for 3DPDF', job_id)

    try:
        cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
        conn.commit()
        logging.info("[!]  Updated Job Condition -> Waiting for 3DPDF")
    except Exception as e:
        error_msg = f"{e}(S4)"
        ERROR_main(db_path, job_id, error_msg, g_cadno)
        return None 
    finally:
        conn.close()


# batchに渡すパスの作成 --------------------------------
# CATIAファイルのパス
def cat_path4batch(list_2, sheet, cn_path):
    cat_base_path = os.path.join(cn_path, "CAT_TEMP")
    cat_row = [item for item in list_2 if sheet in item[0] and item[0].endswith('.CATProduct')]
    cat_full_name = cat_row[0]
    cat_name = cat_full_name[0]
    rev = cat_name.split('_')[-1].split('.')[0]  #F01-02096_PA010_---.CATProduct を_で分割した時の最後の要素 + .で分割した時の最初の要素
    cat_path = os.path.join(cat_base_path, cat_name)
    return cat_path, rev

# 3DPDFの一時保存パス
def pdf_path4batch(cn, sheet, rev, cn_path):
    pdf_base_path = os.path.join(cn_path, "3DPDF_TEMP")
    os.makedirs(pdf_base_path, exist_ok=True) 
    pdf_name = f"{cn}_{sheet}_{rev}.pdf"
    pdf_path = os.path.join(pdf_base_path, pdf_name)
    return pdf_path

# xml のファイルパス
def xml_path4batch(cn, sheet, cn_path):
    xml_base_path = os.path.join(cn_path, "XML", "xml")
    
    xml_name = f"{cn}_{sheet}_Text_Field_Process.xml"
    xml_path = os.path.join(xml_base_path, xml_name)
    return xml_path

# LOGのファイルパス
def log_path4batch(cn_path):
    log_path = os.path.join(cn_path, "LOG")
    os.makedirs(log_path, exist_ok=True) 
    return log_path

# batchファイルの作成
def create_batch(f, cat_path, pdf_path, xml_path, log_path):
    f.write(r'"C:\Program Files\Smartscape\SmartExchange\bin\SmartExchange.exe"^'+ '\n')
    f.write(rf' -i "{cat_path}"^'+ '\n')
    f.write(rf' -o "{pdf_path}"^'+ '\n')
    f.write(rf' -en_rplt_xml "{xml_path}"^'+ '\n')
    f.write(rf' -t "C:\3DPDF\11_TEMPLATES\{g_ver}\A4Y_{g_ver}_main_page_template.pdf"^'+ '\n') # フォントサイズ: 10.5(v1.30)
    f.write(r' -enrich -p "C:\3DPDF\12_SETTINGS\SE_settings_for_minebea_system2.xml" -p_cap true^'+ '\n')
    f.write(rf' -l {log_path}'+ '\n')

def create_batch_small_font(f, cat_path, pdf_path, xml_path, log_path):
    f.write(r'"C:\Program Files\Smartscape\SmartExchange\bin\SmartExchange.exe"^'+ '\n')
    f.write(rf' -i "{cat_path}"^'+ '\n')
    f.write(rf' -o "{pdf_path}"^'+ '\n')
    f.write(rf' -en_rplt_xml "{xml_path}"^'+ '\n')
    if g_ver == "v1.20":
        f.write(rf' -t "C:\3DPDF\11_TEMPLATES\{g_ver}\A4Y_v1.21_main_page_template.pdf"^'+ '\n')
    else:
        f.write(rf' -t "C:\3DPDF\11_TEMPLATES\{g_ver}\A4Y_v1.31_main_page_template.pdf"^'+ '\n') # フォントサイズ:9.5(v1.31)
    f.write(r' -enrich -p "C:\3DPDF\12_SETTINGS\SE_settings_for_minebea_system2.xml" -p_cap true^'+ '\n')
    f.write(rf' -l {log_path}'+ '\n')

def create_batch_dcns(f, cat_path, pdf_path, xml_path, log_path):
    f.write(r'"C:\Program Files\Smartscape\SmartExchange\bin\SmartExchange.exe"^'+ '\n')
    f.write(rf' -i "{cat_path}"^'+ '\n')
    f.write(rf' -o "{pdf_path}"^'+ '\n')
    f.write(rf' -en_rplt_xml "{xml_path}"^'+ '\n')
    f.write(rf' -t "C:\3DPDF\11_TEMPLATES\{g_ver}\A4Y_{g_ver}_main_page_template_dcnmore.pdf"^'+ '\n')
    f.write(r' -enrich -p "C:\3DPDF\12_SETTINGS\SE_settings_for_minebea_system2.xml" -p_cap true^'+ '\n')
    f.write(rf' -l {log_path}'+ '\n')


g_cadno = None  # グローバル変数としてcadnoを定義
g_user_id = None
g_ver = None
def S4_main(cn, cn_path, job_db, job_id, org_list_2, org_list_3_2,  list_3_3, cadno, user_id, ver, template_lists):

    try:
        global g_cadno
        global g_user_id
        global g_ver

        g_cadno = cadno  # グローバル変数に値を代入
        g_user_id = user_id
        g_ver = ver

        bat_full_path = None

        # ジョブDBに "Waiting for 3DPDF"と送る
        logging.info("Waiting for 3DPDF")
        send_condition(job_db, job_id)
        
        # 3DPDFのフォルダがもしあれば、フォルダの中身を消す
        # フォルダなければ無視して次へ
        pdf3d_path = os.path.join(cn_path, "3DPDF_TEMP")

        if os.path.exists(pdf3d_path):
            # フォルダと中身をすべて削除
            shutil.rmtree(pdf3d_path)
            logging.info(f"Successfully deleted folder and all its contents: {pdf3d_path}")

        # batch格納用フォルダ作成
        bat_path = os.path.join(cn_path, "BATCH")
        os.makedirs(bat_path , exist_ok=True) 
        bat_name = f"{cn}.bat" # ファイル名
        bat_full_path = os.path.join(bat_path, bat_name)
        logging.info(f"{bat_full_path}")

        # batchファイルに書いてある各パスの作成
        list_3_2 = [item for item in org_list_3_2 if 'DRS' not in item[0]]
        total_sheets = len(list_3_2)

        # DCN(ECN)の数
        num_dcn = len(list_3_3)

        # CATProductだけ残す
        # CATProduct = 出力される3DPDFの数
        list_2 = [item for item in org_list_2 if 'DRS' not in item[0]]

        pa_sheet_count = total_sheets -1 

        with open(bat_full_path, 'w', encoding='cp932') as f:

            for i in range(1, pa_sheet_count + 1):
                sheet = f"PA{i:02}0"
                cat_path, rev = cat_path4batch(list_2, sheet, cn_path)
                logging.info(cat_path)
                pdf_path      = pdf_path4batch(cn, sheet, rev, cn_path)
                logging.info(pdf_path)
                xml_path      = xml_path4batch(cn, sheet, cn_path)
                logging.info(xml_path)
                log_path      = log_path4batch(cn_path)
                logging.info(log_path)


                flags = [(s, flag) for s, flag in template_lists if s == sheet]
                sheet_flag = flags[0][1]
                logging.info(f"sheet flag: {sheet_flag}")

                if sheet_flag == True:
                    create_batch_small_font(f, cat_path, pdf_path, xml_path, log_path)
                else:
                    create_batch(f, cat_path, pdf_path, xml_path, log_path)

                
                # 【中止】DCN(ECN)が2個以上ある場合は別のテンプレートファイルを使用する
                # if num_dcn >= 2:
                #     create_batch_dcns(f, cat_path, pdf_path, xml_path, log_path)
                # else:
                #     create_batch(f, cat_path, pdf_path, xml_path, log_path)
            
            sheet = "STOCK"
            cat_path, rev = cat_path4batch(list_2, sheet, cn_path)
            pdf_path      = pdf_path4batch(cn, sheet, rev, cn_path)
            xml_path      = xml_path4batch(cn, sheet, cn_path)
            log_path      = log_path4batch(cn_path)

            flags = [(s, flag) for s, flag in template_lists if s == sheet]
            sheet_flag = flags[0][1]
            logging.info(f"sheet flag: {sheet_flag}")

            if sheet_flag == True:
                logging.info("small font")
                create_batch_small_font(f, cat_path, pdf_path, xml_path, log_path)
            else:
                logging.info("nomal font")
                create_batch(f, cat_path, pdf_path, xml_path, log_path)

            # # 【中止】DCN(ECN)が2個以上ある場合は別のテンプレートファイルを使用する
            # if num_dcn >= 2:
            #     create_batch_dcns(f, cat_path, pdf_path, xml_path, log_path, template_lits)
            # else:
            #     create_batch(f, cat_path, pdf_path, xml_path, log_path, template_lits)

        if not os.path.exists(bat_full_path):
            error_msg = "3DPDF BATCH File not Found. (S4)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        
        return bat_full_path
    
    except Exception as e:
        error_msg = f"{e}(S4)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
