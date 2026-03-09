"""
図面v1.20用のxml生成
3DPDF生成時に必要なxmlを作成する

フォルダパス: {公開先}/{cn}/XML
子ディレクトリ：
1. Input : ユーザーが作成したxmlを格納
            (2回目以降の使用を想定)
2. xml : SmartExchangeに渡す用のxmlを格納
         (改行コードがそのままのものであるため、人間からすると非常に見にくい)
         (人間が見やすいように整形すると、今度は3DPDFの改行がうまく実行されなくなる)
3. Output: ユーザー編集用xml
           人間が見やすいように改行されている。            
"""

import os
import glob
import re
import shutil
import pyodbc
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from ERROR import ERROR_main

# === SQL Server 接続設定 =====================================
# TODO サーバーの環境設定
## 本番環境
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = os.getenv("DB_CONFIG") 

# ============================================================

def get_connection(db_config, job_id, job_db):
    """DB接続を確立"""
    try:
        conn_str = (
            f"DRIVER={{{db_config['DRIVER']}}};"
            f"SERVER={db_config['SERVER']};"
            f"DATABASE={db_config['DATABASE']};"
            f"UID={db_config['UID']};"
            f"PWD={db_config['PWD']};"
            f"TrustServerCertificate=yes;"
        )
        return pyodbc.connect(conn_str)
    except pyodbc.Error as ex:
        if ex.args[0] == 'IM002':
            ERROR_main(job_db, job_id, ("Connection Error", "[ODBC Driver 18 for SQL Server] not found."), g_cadno, g_user_id)
        else:
            ERROR_main(job_db, job_id, ("Error", "Failed to Connect to DB.(S1)"), g_cadno, g_user_id)
        return None

# Inputに格納されたファイルを整形する
def format_input(input_path, xml_path, output_path):
    """
    input_path内の全XMLファイルを読み込み、
    value内の改行を &#10; に変換して、
    output_pathに同名で保存する。
    """
    
    # 1. input_pathの中にある .xml ファイルをすべて取得する
    # (*.xml 以外のファイルも対象にする場合は "*" にしてください)
    input_files = glob.glob(os.path.join(input_path, "*.xml"))

    # 置換用関数 (value="..." の中身だけを処理)
    def restore_newlines(match):
        target_str = match.group(0)
        # valueの中の実際の改行を文字参照コードに置換
        return target_str.replace('\n', '&#10;').replace('\r', '&#13;')

    # 2. ファイルごとにループ処理
    for file_path in input_files:
        try:
            # ファイル名を取得 (例: "test.xml")
            file_name = os.path.basename(file_path)
            
            # InputをそのままOutputに入れる
            shutil.copy2(file_path, os.path.join(output_path, file_name))

            # --- 読み込み ---
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # --- 置換処理 ---
            # ファイル全体を replace するとタグ構造が壊れるため、
            # 正規表現で value="..." の中だけをターゲットにします。
            content = re.sub(r'value=".*?"', restore_newlines, content, flags=re.DOTALL)
            
            # --- 保存 ---
            # XML/xmlファイルに保存
            save_path = os.path.join(xml_path, file_name)
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")


int_part = None
def search_bom(job_db, job_id, cursor, cn):
    global int_part

    # 部品名を取得する
    int_part_sql = """
        SELECT
            INT_PARTNAME
        FROM [innovator].PART
        WHERE KEYED_NAME = ? AND IS_CURRENT = 1
    """
    cursor.execute(int_part_sql, cn)
    int_part_result = cursor.fetchone()
    int_part = int_part_result[0]
    
    # BOM構成の取得
    bom_sql = """
        WITH BOM_Hierarchy AS (
            -- 1. 起点の部品を取得
            SELECT  
                CAST(NULL AS NVARCHAR(128)) AS grandparent_keyed_name, 
                CAST('' AS NVARCHAR(128)) AS parent_keyed_name, 
                CAST('' AS NVARCHAR(128)) AS parent_partname,
                ID AS child_id, 
                KEYED_NAME AS child_keyed_name,
                INT_PARTNAME AS child_partname,
                0 AS level
            FROM [innovator].PART
            WHERE KEYED_NAME = ? AND IS_CURRENT = 1

            UNION ALL

            -- 2. 再帰部
            SELECT 
                bh.parent_keyed_name AS grandparent_keyed_name,
                bh.child_keyed_name AS parent_keyed_name,
                bh.child_partname AS parent_partname,
                p.ID AS child_id,
                p.KEYED_NAME AS child_keyed_name,
                p.INT_PARTNAME AS child_partname,
                bh.level + 1
            FROM [innovator].PART_BOM pcad
            INNER JOIN BOM_Hierarchy bh ON pcad.SOURCE_ID = bh.child_id
            INNER JOIN [innovator].PART p ON pcad.RELATED_ID = p.ID
            WHERE bh.level < 30 AND p.IS_CURRENT = 1
        )
        -- 3. 最終出力
        SELECT 
            CASE 
                WHEN grandparent_keyed_name IS NULL OR grandparent_keyed_name = '' 
                THEN parent_keyed_name 
                ELSE grandparent_keyed_name 
            END AS grandparent_keyed_name,
            parent_keyed_name,
            parent_partname,
            child_keyed_name
        FROM 
            BOM_Hierarchy bh
        WHERE 
            level > 0
            AND NOT EXISTS (
                SELECT 1 
                FROM [innovator].PART_BOM sub 
                WHERE sub.SOURCE_ID = bh.child_id
            )
            AND child_keyed_name LIKE 'P%'
        ORDER BY 
            1, 2, 4;
    """

    cursor.execute(bom_sql, cn)
    bom_result = cursor.fetchall()
    return bom_result


## 製品図(F始まり)の場合 ----------------------------------------
def msp_query_B1(job_db, job_id, cursor, cn):

    msp_sql = """
        -- 1. ターゲットとなる親部品と、その工程セット(SR_CODE)を定義
        WITH TargetPart AS (
            SELECT ? AS TargetName -- ここでCNを定義
        ),
        TargetSRCode AS (
            -- 起点部品名と一致する工程計画からSR_CODEを取得
            SELECT 
                s.KEYED_NAME AS SR_CODE
            FROM [innovator].ORG_PROCESSPLAN_RD pp
            INNER JOIN [innovator].ORG_PROCESSSET_RD s ON pp.OLD_SR_CODE = s.ID
            CROSS JOIN TargetPart
            WHERE pp.KEYED_NAME = TargetPart.TargetName 
            AND pp.IS_CURRENT = 1
        ),
        -- 部品情報(親+子)を先にまとめて取得(ここではSR_CODEはまだ結合しない)
        PartInfo AS (
            -- 2. 親部品自身の情報を取得
            SELECT DISTINCT
                0 AS SORT_ORDER,
                p.KEYED_NAME,
                cr.CUST_REQ_CODE,
                cr.MATERIAL_PROC_NAME,
                cr.MATERIAL_PROC_SPEC,
                cr.TYPE_CLASS,
                cr.HARDNESS_MIN,
                cr.HARDNESS_MAX,
                cr.HARDNESS_UNIT,
                cr.NOTES
            FROM [innovator].PART p
            INNER JOIN [innovator].ORG_PART_CUSTOMER_REQUEST pcr ON p.ID = pcr.SOURCE_ID
            INNER JOIN [innovator].ORG_CUSTOMER_REQUEST cr ON pcr.RELATED_ID = cr.ID
            CROSS JOIN TargetPart
            WHERE p.KEYED_NAME = TargetPart.TargetName 
            AND p.IS_CURRENT = 1

            UNION ALL

            -- 3. 子部品の情報を取得
            SELECT DISTINCT
                1 AS SORT_ORDER,
                p.KEYED_NAME,
                cr.CUST_REQ_CODE,
                cr.MATERIAL_PROC_NAME,
                cr.MATERIAL_PROC_SPEC,
                cr.TYPE_CLASS,
                cr.HARDNESS_MIN,
                cr.HARDNESS_MAX,
                cr.HARDNESS_UNIT,
                cr.NOTES
            FROM [innovator].PART p
            INNER JOIN [innovator].PART_BOM b ON p.ID = b.RELATED_ID
            INNER JOIN [innovator].PART parent ON b.SOURCE_ID = parent.ID
            INNER JOIN [innovator].ORG_PART_CUSTOMER_REQUEST pcr ON p.ID = pcr.SOURCE_ID
            INNER JOIN [innovator].ORG_CUSTOMER_REQUEST cr ON pcr.RELATED_ID = cr.ID
            CROSS JOIN TargetPart
            WHERE parent.KEYED_NAME = TargetPart.TargetName 
            AND parent.IS_CURRENT = 1 
            AND p.IS_CURRENT = 1
        )

        -- メインクエリ: SR_CODEを主軸にし、PartInfoをLEFT JOINする
        SELECT
            tsr.SR_CODE,
            pi.KEYED_NAME,
            pi.CUST_REQ_CODE,
            pi.MATERIAL_PROC_NAME,
            pi.MATERIAL_PROC_SPEC,
            pi.TYPE_CLASS,
            pi.HARDNESS_MIN,
            pi.HARDNESS_MAX,
            pi.HARDNESS_UNIT,
            pi.NOTES
        FROM TargetSRCode tsr
        -- ここで LEFT JOIN を使い、ON 1=1 で全結合を試みる
        -- これにより、PartInfoが0件でも tsr (SR_CODE) の行は残る
        LEFT JOIN PartInfo pi ON 1=1
        ORDER BY 
            pi.SORT_ORDER, 
            pi.KEYED_NAME;
    """
    try:
        cursor.execute(msp_sql, cn)
        result = cursor.fetchall()

        special_result = []
        material_result = []

        for item in result:
            # 客先要求コード が 'FM' で始まる場合
            if item[2] is None:
                special_result = result
                continue
            elif item[2].startswith('FM'):
                material_result.append(item)

            # それ以外
            else:
                special_result.append(item)

        return material_result, special_result
    except Exception as e:
        logging.error(f"{e}")
        return None, None



# TODO: CUST.DWG.NOを入れる (STOCKのみに記載)

# サブアッシーの場合
# 1. PARTから社内型式番号を取得
# 2. 社内型式番号の一部を切り取り、PARTの検索をかける
# 3. 見つかった場合 → def dwg_infoを呼び出す
# 4. 見つからなかった場合 → サンプルを添付する

# トップアッシーの場合
# 1. dwg_infoを呼び出す

# dwg_info:
# 1. ORG_CUSTOMERSPEC_RDについて
# CUST.DGW.NO: DWG
# PROCUREMENT: リビジョン入り かつ PROCURENT のものを添付、なければPROCUREMENTの全てを添付
# S-DWG: SDWG
# トップアッシーフラグが立っている場合: "BEARING CARTRIDGE: ****"
#                     立っていない場合：NMB_PN:

# None を返してエラーが発生する場合は、サンプルを添付

# def check_spec(cn):

    


# def dwg_info(job_db, job_id, cursor, cn):

#     if cn.startswith('F'):
#         return cn


#     dwg_sql = """
#     SELECT
#     osc.SPEC_NO,
#     p.CUST_PARTNO
# FROM
#     [innovator].PART p
# INNER JOIN
#     [innovator].PART_SPECCUSTOMER ps ON p.ID = ps.SOURCE_ID
# INNER JOIN
#     [innovator].ORG_SPECCUSTOMER_RD osc ON ps.RELATED_ID = osc.ID
# WHERE
#     p.KEYED_NAME = ? 
#     AND p.IS_CURRENT = 1
#     AND osc.SPEC_TYPE = '58EC9E4742C04D0A8EE4886116EEDAFC';
#     """

# E6A3D536B1B94DE88BB21D05A9BD72A7: DWG
# BF2120FEC78942318B8FB4ADAEBFA817: PROCUREMENT
# 58EC9E4742C04D0A8EE4886116EEDAFC: S-DWG


## ------------------------------------------------------------


## 子部品図の場合 ----------------------------------------------
g_bom_result = None
def msp_query(job_db, job_id, cursor, cn):
    
    # BOM情報を取得する
    # [(図面のCN, 子部品, 社内型式名, 材料CN)]
    bom_result = search_bom(job_db, job_id, cursor, cn)

    # bom_resultの"parent_keyed_name"に図面CNが含まれていない場合は強制的に追加
    exists = any(row[1] == cn for row in bom_result)

    if not exists:
        bom_result.append((cn, cn, int_part, None))

    
    global g_bom_result
    g_bom_result = bom_result



    # 材料情報を取得するSQL
    # [{(親部品, 子部品, 社内型式名, 材料): ( 購買仕様書, 材料名称, 材料スペック), {(親部品, 子部品, 社内型式名, 材料): (購買仕様書, 材料名称, 材料スペック)...}]
    mat_sql = """
        SELECT
            s.KEYED_NAME AS PURCHASE_SPEC,
            om.MATERIAL_NAME,
            om.MATERIAL_SPEC
        FROM 
            [innovator].ORG_PARTATTR_MATERIAL m
        INNER JOIN 
            [innovator].ORG_OLDMATERIAL_RD om ON m.OLD_CODE = om.ID
        LEFT JOIN 
            [innovator].ORG_SPECCOMPANY_RD s  ON om.PROCUMENT_SPEC = s.ID
        WHERE 
            m.KEYED_NAME = ? -- 起点の親部品
            AND m.IS_CURRENT = 1;
    """
    material_result = []

    for mat in (bom_result or []): # bom_resultが空の場合：forループをスキップ

        if mat[3] is None: # 材料コードがNoneの場合はスキップ
            continue
        
        # ?に材料CNを挿入(PM1-****)
        try:
            cursor.execute(mat_sql, mat[3])
            mat_info = cursor.fetchall()
        except Exception as e:
            logging.error(f"{e}")
            continue

        # mat_info = (購買仕様書, 材料名称, 材料スペック)
        if mat_info:
            # 辞書を作成してリストに追加
            # キーを (親部品, 子部品, 材料) のタプルにする
            entry = tuple(mat) + tuple(mat_info[0])
            material_result.append(entry)

    # 特殊工程 (熱処理, 表面処理, 非破壊検査)
    sp_sql = """
        SELECT
            s.KEYED_NAME,  --旧SR_CODE (16N)
            pi.SHEET,   -- SHEET名(PA010)
            sp.SPECIAL_PROCESS_TYPE,  --特殊工程区分 (H)
            sp.KEYED_NAME,  --特殊工程コード (C13)
            sp.NAME AS PROCESS_NAME, --処理名称 (CURBURIZING)
            c1.KEYED_NAME AS SPEC_COM,  -- 社内規格1 (RE41213)
            c2.KEYED_NAME AS SPEC_COM2, -- 社内規格2
            sp.PROCESS_SPEC, -- 処理スペック(AMS2759/7)
            sp.TYPE_CLASS, -- タイプ・クラス (CL.3 TY.3)
            sp.SURFACE_HARDNESS, -- 表面硬さ (59-63 HRC)
            sp.THICKNESS, -- 膜厚
            sp.SAMPLING_FREQUENCY, -- サンプリング周期 (ALL)
            sp.SHANK_HARDNESS, -- シャンク硬さ
            sp.HEAD_HARDNESS, -- 頭部硬さ
            sp.EFFECTIVE_DEPTH -- 有効浸炭硬さ
        FROM 
            [innovator].ORG_PROCESSPLAN_RD pp
        INNER JOIN 
            [innovator].ORG_PROCESSPLAN_PROSEQ_RD ps ON pp.ID = ps.SOURCE_ID
        INNER JOIN 
            [innovator].ORG_PROCESSSEQUENCE_RD pi  ON ps.RELATED_ID = pi.ID
        INNER JOIN 
            [innovator].ORG_PROCESSSET_RD s  ON pp.OLD_SR_CODE = s.ID
        LEFT JOIN 
            [innovator].ORG_SPECIAL_PROCESS_RD sp  ON pi.SPECIAL_PROCESS = sp.ID
        LEFT JOIN 
            [innovator].ORG_SPECCOMPANY_RD c1  ON sp.SPEC_COMPANY1 = c1.ID
        LEFT JOIN 
            [innovator].ORG_SPECCOMPANY_RD c2  ON sp.SPEC_COMPANY2 = c2.ID
        WHERE 
            pp.KEYED_NAME = ?
            AND pp.IS_CURRENT = 1;
            -- AND pi.SPECIAL_PROCESS IS NOT NULL;
        """

    special_result = []
    for bom in (bom_result or []): # bom_resultが空の場合：forループをスキップ
        try:
            cursor.execute(sp_sql, bom[1])
            special_info = cursor.fetchall()

            if special_info:  
                # 辞書を作成してリストに追加
                # キーを (親部品, 子部品, 材料) のタプルにする
                spc_entry = (bom[1],) + tuple(special_info[0])
                special_result.append(spc_entry)
        except Exception as e:
            logging.error(f"{e}")
            continue

    return material_result, special_result

## ------------------------------------------------------------

def format_name(full_name: str) -> str:
    """Haruka Matsuta -> H. Matsuta"""
    try:
        first, last = full_name.split(' ', 1)
        return f"{first[0]}. {last}"
    except (ValueError, IndexError):
        return full_name


def bom_sort_key(item):
    val = item[1]  # index1の値を取得（例: 'A05...', 'F...', 'C10...'）
    first_char = val[0]
    
    # 1. 第一優先：F, A, C の順序を定義
    order = {'F': 0, 'A': 1, 'C': 2}
    # F, A, C 以外が含まれる場合に備えて、大きな数値（9）をデフォルトに設定
    priority1 = order.get(first_char, 9)
    
    # 2. 第二優先：A, C の中の数字部分
    # Fの場合は数字がない想定、または比較不要なら 0 に設定
    priority2 = 0
    if first_char in ['A', 'C'] and len(val) >= 3:
        try:
            # 次の2文字を数値として取り出す
            priority2 = int(val[1:3])
        except ValueError:
            priority2 = 99  # 数値に変換できない場合の予備
            
    return (priority1, priority2)

def is_sortable(data_list):
    """
    ソートを実行しても安全かチェックする関数
    条件:
    1. リストが空ではない
    2. リスト内の要素の index 1 が None ではない
    """
    # 条件1: リストが None または 空 の場合は False
    if not data_list:
        return False

    # 条件2: リストの中身を走査し、index 1 が None のものが1つでもあれば False
    for item in data_list:
        if item[1] is None:
            return False
            
    # 全てクリアしたら True
    return True

# 製品図の場合
def build_msp_B1(job_db, job_id, cn, material_result, special_result):
    """
    v1.20図面左下の
    材料 & 特殊工程 の体裁を整える
    
    ルール：
    ・材料 -> 図面CN直下・子供関係なく、全Sheet表示
    ・特殊工程 -> 未実施の工程についても全て表示
    注意点：
    ・組立工程でまだ登場していない部品についても、すべて表示されてしまう。
    """
    msp_text = ""
    
    try:
        # BOM情報を取得する
        # [(図面のCN, 子部品, 社内型式名, 材料CN)]
        conn = get_connection(DB_CONFIG, job_id, job_db)
        if not conn: return
        cursor = conn.cursor()

        bom_result = search_bom(job_db, job_id, cursor, cn)
        
        # bom_resultの"parent_keyed_name"に図面CNが含まれていない場合は強制的に追加
        exists = any(row[1] == cn for row in bom_result)
        if not exists:
            bom_result.append((cn, cn, int_part, None))

        # 結果をソートする (F> A> C かつ、上2桁が小さい順)
        bom_result.sort(key=bom_sort_key)        
        if is_sortable(special_result):
            special_result.sort(key=bom_sort_key)
        if is_sortable(material_result):
            material_result.sort(key=bom_sort_key)
    
        # MSPの中身
        for bom in bom_result:
            # タイトル (e.g. F01-02146 (Finish))
            if bom[1].startswith("F"):
                partname = "Finish"
            else:
                partname = bom[2]
            
            msp_text += f"{bom[1]} ({partname})\n"

            # 材料名が存在するか確認
            for item in material_result:
                if item[1] == bom[1]:
                    # MATERIAL: 材料名称(item[3]), 処理スペック(item[4]), タイプ(item[5]), 注記(item[9])
                    elements = [str(item[i]).strip() for i in [3, 4, 5, 9] if item[i] and str(item[i]).strip()]

                    # リストの中身を "," でつなぐ
                    combined_text = ", ".join(elements)
                    
                    # 末尾に "." を付ける
                    # 末尾が "." で終わっていれば、付けない
                    if combined_text and not combined_text.endswith("."):
                        material_text = combined_text + "."
                    else:
                        material_text = combined_text
                    
                    msp_text += f"MATERIAL: {material_text}\n"

            for elem in special_result:
                if elem[1] == bom[1]:
                    # 熱処理
                    if elem[2].startswith("FH"):
                        # 1. 各要素を文字列にして前後の空白を削除
                        # elem[i] が None の場合は空文字にする
                        e = [str(elem[i]).strip() if elem[i] is not None else "" for i in range(10)]

                        # 2. ハイフンで繋ぐ部分 (elem[6]-elem[7]) の処理
                        # elem[7] がある場合は "6-7"、ない場合は "6" だけにする

                        if e[6] and e[7]:
                            hardness = f"{e[6]}-{e[7]} {e[8]}"
                        elif e[6]:
                            hardness = f"{e[6]} {e[8]}"
                        else:
                            hardness = ""
                        
                        # 3. カンマで繋ぐ要素をリストにまとめる
                        # 中身があるものだけを採用する 
                        #body_parts = [p for p in [e[4], e[5], hardness, e[9]] if p]
                        base_text = [e[4], e[5], hardness if hardness else "", e[9]]
                        body_parts = [
                            p if p.endswith('.') else p + '.' 
                            for p in base_text 
                            if p
                        ]
                        # 4. 全体を組み立てる
                        line = f"{e[3]}: {', '.join(body_parts)}"
                        msp_text += line + "\n"
                    
                    # 表面処理
                    elif elem[2].startswith("FP"):
                        elements = [str(elem[i]).strip() for i in [4, 5, 9] if elem[i] and str(elem[i]).strip()]

                        # リストの中身を "," でつなぐ
                        sp_combined_text  = ", ".join(elements) 
                        
                        if sp_combined_text and not sp_combined_text.endswith("."):
                            sp_combined_text  = ", ".join(elements) + "."
                        
                        msp_text += f"{elem[3]}: {sp_combined_text}\n"

                    # 非破壊検査
                    elif elem[2].startswith("FI"):
                        elements = [str(elem[i]).strip() for i in [4, 5, 9] if elem[i] and str(elem[i]).strip()]
                        
                        # リストの中身を "," でつなぐ
                        fi_combined_text = ", ".join(elements)
                        
                        # 末尾に "." を付ける
                        # 末尾が "." で終わっていれば、付けない
                        if fi_combined_text and not fi_combined_text.endswith("."):
                            fi_text = fi_combined_text + "."
                        else:
                            fi_text = fi_combined_text
                        
                        if elem[3].startswith("MAGNETIC PARTICLE"):
                            msp_text += f"M.I.P: {fi_text}\n"
                        elif elem[3].startswith("FLUORESCENT PENETRANT"):
                            msp_text += f"F.P.I: {fi_text}\n"
                        else:
                            msp_text += f"{elem[3]}: {fi_text}\n"
            msp_text += "________________________________\n"
        return msp_text    
    
    except Exception as e:
        error_msg = f"{e}"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
    
# 子部品図の場合(A, C始まりのCN)
def build_msp(job_db, job_id, cn, material_result, special_result):
    msp_text = ""

    try:
        bom_result = g_bom_result

        # 結果をソートする (F> A> C かつ、上2桁が小さい順)
        bom_result.sort(key=bom_sort_key)

        for bom in bom_result:
            # タイトル (e.g. A42-0473(SPH)
            if "LINER" in bom[2]:    # LINERの場合はその親を含める (A42-04073_C82-01608)
                item_name = bom[0] + "_" + bom[1]
                partname = "LINER"
            else:
                item_name = bom[1]
                partname = bom[2]
            msp_text += f"{item_name}({partname})\n"

            # 材料
            for material in material_result:
                if material[1] == bom[1]:
                    # MATERIAL: 社内規格, 材料名称, 処理スペック
                    elements = [str(material[i]).strip() for i in [4, 5, 6] if material[i] and str(material[i]).strip()]

                    # リストの中身を "," でつなぐ
                    combined_text = ", ".join(elements)

                    # 末尾に "." を付ける
                    # 末尾が "." で終わっていれば、付けない
                    if combined_text and not combined_text.endswith("."):
                        material_text = combined_text + "."
                    else:
                        material_text = combined_text
                    
                    msp_text += f"MATERIAL: {material_text}\n"

            for elem in special_result:
                if elem[0] == bom[1]:
                    
                    # 熱処理
                    # HEATTREAT: 社内規格, 硬さ, 処理スペック, タイプ
                    if elem[3] == "H":  # 特殊工程区分

                        # 1. 各要素を文字列にして前後の空白を削除
                        # elem[i] が None の場合は空文字にする
                        e = [str(elem[i]).strip() if elem[i] is not None else "" for i in range(16)]
                        
                        # 2. 処理名称
                        # CARBURIZING: 社内規格, 硬さ, 処理スペック, タイプ, 有効浸炭深さ, ねじ硬さ, 頭部硬さ
                        if e[5] == "CARBURIZING":

                            # 3. カンマで繋ぐ要素をリストにまとめる
                            # 中身があるものだけを採用する 
                            case_depth = f"CASE DEPTH {e[15]}"
                            shank_hardness = f"SHANK HARDNESS {e[13]}"
                            head_hardness = f"HEAD HARDNESS {e[14]}"
                            
                            body_parts = [p for p in [e[6], e[10], e[7], e[8], e[9], case_depth, shank_hardness, head_hardness] if p]
                            
                            # 4. 全体を組み立てる
                            line = f"CARBURIZING: {', '.join(body_parts)}"
                            if line and not line.endswith("."):
                                line = line + "."
                            
                            msp_text += line + "\n"

                        else:
                            # 3. カンマで繋ぐ要素をリストにまとめる
                            # 中身があるものだけを採用する 
                            body_parts = [p for p in [e[6], e[7], e[10], e[8], e[9], e[5]] if p]
                            
                            # 4. 全体を組み立てる
                            line = f"HEAT TREAT: {', '.join(body_parts)}"
                            if line and not line.endswith("."):
                                line = line + "."
                            
                            msp_text += line + "\n"
                    
                    # 表面処理
                    # 処理名称：社内規格, 厚さ, 処理スペック, タイプ
                    elif elem[3] == "P":  # 特殊工程区分

                        elements = [str(elem[i]).strip() for i in [6, 7, 11, 8, 9] if elem[i] and str(elem[i]).strip()]

                        # リストの中身を "," でつなぐ
                        sp_combined_text  = ", ".join(elements) 
                        
                        if sp_combined_text and not sp_combined_text.endswith("."):
                            sp_combined_text  = ", ".join(elements) + "."
                        
                        msp_text += f"{elem[5]}: {sp_combined_text}\n"

                    # 非破壊検査
                    elif elem[3] == "I":
                        elements = [str(elem[i]).strip() for i in [6, 7, 8, 9, 12] if elem[i] and str(elem[i]).strip()]
                        
                        # リストの中身を "," でつなぐ
                        fi_combined_text = ", ".join(elements)
                        
                        # 末尾に "." を付ける
                        # 末尾が "." で終わっていれば、付けない
                        if fi_combined_text and not fi_combined_text.endswith("."):
                            fi_text = fi_combined_text + "."
                        else:
                            fi_text = fi_combined_text
                        
                        if elem[3].startswith("MAGNETIC PARTICLE"):
                            msp_text += f"M.I.P: {fi_text}\n"
                        elif elem[3].startswith("FLUORESCENT PENETRANT"):
                            msp_text += f"F.P.I: {fi_text}\n"
                        else:
                            msp_text += f"{elem[5]}: {fi_text}\n"
            msp_text += "________________________________\n"
        return msp_text    
    
    except Exception as e:
        error_msg = f"{e}"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)


def create_xml_file(sheet, subsq, cn, list_3_1, list_3_2, list_3_3, list_4, xml_path, job_db, job_id, material_result, special_result, op, template_flag):
    """【共通】XMLファイルを生成するメイン関数"""
    partno, partname, authority, productclass = list_3_1[0]
    approval_info = list_3_2[0]   # DRS(0番目の要素)のみを取得するだけでOK!

    if not approval_info or None in approval_info:
        ERROR_main(job_db, job_id, "Creator, Checker, Approver, Date Information not Found. Please Register those Information in Innovator.(S3)", g_cadno, g_user_id)
        return

    # 基本情報整理
    creator  = format_name(approval_info[1])  # 作成者：最終更新者=作成者である前提
    checker  = format_name(approval_info[2])  # 検図者
    approver = format_name(approval_info[3])  # 承認者
    rev      = approval_info[7]               # リビジョン
    create_date   = datetime.now().strftime('%Y/%m/%d')                          # 今の日付
    check_date    = (approval_info[5] + timedelta(hours=9)).strftime('%Y/%m/%d')  # 検図日(DRSが基準)
    approval_date = (approval_info[6] + timedelta(hours=9)).strftime('%Y/%m/%d')  # 承認日(DRSが基準)

    # DCN
    num_dcn = len(list_3_3)
    dcn_val = sorted(list_3_3, key=lambda item: item[1])[0][0] if num_dcn >= 2 else list_3_3[0]
    dcnmore = f"+{num_dcn - 1} doc(s)" if num_dcn >= 2 else None

    
    # 工程情報(WI / PRS)
    ## PRS  -> 図面左上の工程一覧
    ## WI   -> 図面右側の工程注記
    
    process_info = sorted([row for row in list_4 if row[0] == sheet], key=lambda r: r[1])
    
    # SR Code
    sr_code = None

    if cn.startswith("F"):
        sr_code = special_result[0][0]    
    else:
        for special in special_result:
            # special 例: ('C11-02713', '16N', 'PA080', 'H', 'C13', 'CARBURIZING', 'RE41213'...)
            if special[0] == cn:
                sr_code = special[1]
                break

    process_parts = [f"S/R No.: RE22{sr_code}\nOP |CODE|NAME"] # PRS
    notes_parts = []  # WI

    
    if not any(row[4] and row[4].strip() for row in process_info):
        notes_parts.append("N/A")
        for row in process_info:
            process_parts.append(f"{op:02}0|{row[2]}|{row[3]}") 
            op = op + 1
    else:
        for row in process_info:
            process_parts.append(f"{op:02}0|{row[2]}|{row[3]}") 
            op = op + 1
            
            if row[4]:

                # Requirement 関連の注記
                pattern = r'(?=< ?(?:REQUIREMENT|客先要求))'
                body = row[4].strip()
                header = f"■#{row[2]} {row[3]}■"
                footer = "_" * 70

                if row[3] == "STOCK":
                    dwg_info = (
                        "CUST.DWG.NO: XXXXXXXX\n" 
                        + "PROCUREMENT SPEC.: XXXXXXXX\n" 
                        + "S-DWG: XXXXXXXX\n" 
                        + "CUST.P/N: XXXXXXXX\n" 
                        + "NMB P/N: XXXXXXXX\n"
                        + "BEARING CARTRIDGE: XXXXXXXX\n")
                    #notes_parts.append(dwg_info)

                    if body.lstrip().startswith(("<REQUIREMENT", "< REQUIREMENT", "<客先要求", "< 客先要求")): # STOCKの注記が無く、製品要求から始まる場合
                        notes_parts.append(body) 
                    else:
                        if re.search(pattern, body): # STOCKの注記がある + 製品要求もある場合
                            parts = re.split(pattern, body)
                            new_body = (footer + "\n").join(parts) # STOCKの注記と製品要求を区切る
                        
                            notes_parts.append(header)
                            notes_parts.append(new_body)
                        else: # それ以外
                            notes_parts.append(header)
                            notes_parts.append(body)

                    # ---------------------------------

                else: # STOCK以外の図面
                    # ■を直接文字列に入れる                    
                    notes_parts.append(header)
                    notes_parts.append(body)
                    notes_parts.append(footer)


    # Material and Special Process (図面左下)
    # 製品図の場合
    if cn.startswith("F"):
        msp_str = build_msp_B1(job_db, job_id, cn, material_result, special_result)
        print(msp_str)
    else: # 子部品図の場合
        msp_str = build_msp(job_db, job_id, cn, material_result, special_result)

    # XML要素組み立て
    root = ET.Element("Fields")
    field_data = {
        'PRS': "\n".join(process_parts),
        'PRS-L': "\r\n________________________________\r\n________________________________",
        'MSP': msp_str,
        'WI': "\n".join(notes_parts),
        'DWGNO': f"{cn}_DRS01",
        'SUBSQ': subsq,
        'DWGREV': rev,
        'PARTNO': partno,
        'PARTNAME': partname,
        'DCN': dcn_val,
        'DRAWN': creator,
        'DRAWNDATE': create_date,
        'CHECKER': checker,
        'CHECKEDDATE': check_date,
        'APPROVER': approver,
        'APPROVEDDATE': approval_date,
        'PRODUCTCLASSCODE': productclass,
        'AUTHORITYDATA': authority,
    }
    if dcnmore: field_data['DCNMORE'] = dcnmore

    for k, v in field_data.items():
        ET.SubElement(root, "Field", attrib={'key': k, 'value': str(v)})

    # 保存 (読み取り用)
    tree = ET.ElementTree(root)
    xml_name = f"{cn}_{sheet}_Text_Field_Process.xml"
    xml_full_path = os.path.join(xml_path, xml_name)
    ET.indent(tree)
    tree.write(xml_full_path, encoding='utf-8', xml_declaration=True)

    # 工程注記が44行を超える場合は、フラグを立てて3DPDFのテンプレートファイルを差し替える
    line_count = len('\n'.join(notes_parts).splitlines())
    
    limit = 44
    is_over_limit = line_count > limit
    template_flag.append((sheet, is_over_limit))
    # print(f'Line Count: {line_count}')
    # print(f"{'\n'.join(notes_parts)}")
    
    return op, template_flag

def build_template_list_from_input(input_path):
    """
    Inputフォルダ内のXMLファイルから、各シートのWIフィールドの行数を読み取り、
    template_list (シート名, 44行超過フラグ) を生成する。
    """
    limit = 44
    template_list = []
    input_files = sorted(glob.glob(os.path.join(input_path, "*.xml")))

    for file_path in input_files:
        try:
            file_name = os.path.basename(file_path)
            # ファイル名から sheetを抽出 (例: CN_PA010_Text_Field_Process.xml -> PA010)
            parts = file_name.split('_')
            # 2番目の要素がシート名 (PA010, PA020, ..., STOCK)
            if len(parts) >= 2:
                sheet = parts[1]
            else:
                continue

            tree = ET.parse(file_path)
            root = tree.getroot()

            wi_value = ""
            for field in root.findall("Field"):
                if field.get("key") == "WI":
                    wi_value = field.get("value", "")
                    break

            # &#10; を改行として扱い行数をカウント
            line_count = len(wi_value.splitlines()) if wi_value else 0
            is_over_limit = line_count > limit
            template_list.append((sheet, is_over_limit))

        except Exception as e:
            logging.warning(f"Failed to read WI from {file_path}: {e}")

    return template_list


def format_xml(output_file):
    with open(output_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # エスケープされた改行コード( &#10; )を、実際の改行( \n )に置換する
    content = content.replace('&#10;', '\n')

    # 念のためキャリッジリターン( &#13; )があれば削除または置換
    content = content.replace('&#13;', '') 

    # ファイルを上書き保存する
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        logging.info(f"Failed To Save Output File: {e}")


def generate_all_sheets(list_3_1, list_3_2, list_3_3, list_4, cn, xml_path, output_path, job_db, job_id, material_result, special_result):
    """PAとSTOCKの全シートを回す共通ループ"""
    total = len(list_3_2) -1  # SHEETの数を決定(DRSは不要なので-1)
    
    sheets = [f"PA{i:02}0" for i in range(1, total)] + ["STOCK"]

    template_flag = []

    org_op = 1
    for i, sheet in enumerate(sheets, 1):
        subsq = f"{sheet}({i}/{total})"
        op, template_list = create_xml_file(sheet, subsq, cn, list_3_1, list_3_2, list_3_3, list_4, xml_path, job_db, job_id, material_result, special_result, org_op, template_flag)
        org_op = op

    # xmlのファイルを丸ごとOutputにコピーする
    copyed_files = glob.glob(os.path.join(xml_path, "*.*"))
    
    if not copyed_files:
        error_msg = "Failed to Create XML.(S3)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
    else:
        for f in copyed_files:
            if os.path.isfile(f):
                shutil.copy2(f, os.path.join(output_path, os.path.basename(f)))
    
    # 整形したxmlを作成し、Outputフォルダに保存
    output_files = glob.glob(os.path.join(output_path, "*.*"))
    for output_f in output_files:
        format_xml(output_f)

    return template_list


# --- Main Logic ---
g_cadno = None
g_user_id = None

def S3_2_main(job_db, job_id, list_3_1, list_3_2, list_3_3, list_4, cn, cn_path, cadno, user_id):
    global g_cadno, g_user_id
    g_cadno, g_user_id = cadno, user_id

    # フォルダ準備
    xml_base_path = os.path.join(cn_path, "XML")
    os.makedirs(xml_base_path, exist_ok=True)

    # コンピューターが読み取る用のXMLのパス
    xml_path = os.path.join(xml_base_path, "xml")
    if os.path.exists(xml_path):
        shutil.rmtree(xml_path)
    os.makedirs(xml_path, exist_ok=True)
    
    # ユーザーインプット用パス
    input_path = os.path.join(xml_base_path, "Input")
    os.makedirs(input_path, exist_ok=True)
    
    # アウトプットパス
    output_path = os.path.join(xml_base_path, "Output")
    os.makedirs(output_path, exist_ok=True)

    # アウトプットについては、時間ごとにフォルダ分けする。
    output_timepath = os.path.join(output_path, datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(output_timepath, exist_ok=True)

    # Inputのフォルダにファイルがあるかを確認
    if os.path.exists(input_path) and len(os.listdir(input_path)) > 0:
        """
        1. Inputフォルダ内のファイルをxml読み取り用に整形
        2. それをxmlに保管
        3. InputにあるファイルはそのままOutputフォルダに保存
        注) Inputフォルダ内のファイルは削除しない !!
        """
        format_input(input_path, xml_path, output_timepath)
        logging.info("Input XML file(s) are used !")

        # Inputフォルダ内のXMLからWIの行数を読み取り、template_listを生成
        template_list = build_template_list_from_input(input_path)
        return template_list

    else:
        # Innovatorの情報をもとにxmlを作成
        try:
            conn = get_connection(DB_CONFIG, job_id, job_db)
            if not conn: return
            cursor = conn.cursor()

            # クエリ実行（F始まりか否かで分岐）
            if cn.startswith('F'):

                # msp_query_B1 の戻り値を整理して取得
                material_result, special_result = msp_query_B1(job_db, job_id, cursor, cn)
            else:
                # msp_query の既存ロジックを使用
                material_result, special_result = msp_query(job_db, job_id, cursor, cn)

            # XML生成実行
            template_list = generate_all_sheets(list_3_1, list_3_2, list_3_3, list_4, cn, xml_path, output_timepath, job_db, job_id, material_result, special_result)
            logging.info("XML File(s) are Successfully Created !")

            return template_list

        except Exception as e:
            ERROR_main(job_db, job_id, f"{e}(S3)", g_cadno, g_user_id)
    
        finally:
            if conn: conn.close()