"""
ユーザーがInnovatorのアクティブユーザーであるかを確認し、
クエリで、図面に必要な情報を取得する
"""
import os
import sys
import pyodbc
import sqlite3
import logging


# TODO サーバーの環境設定
# === SQL Server 接続設定 =====================================

from dotenv import load_dotenv
load_dotenv()

# サーバー本番環境設定ファイル
DB_CONFIG = os.getenv("DB_CONFIG")

# ============================================================


# エラー処理用関数 ====================================

from ERROR import ERROR_main

# ===================================================

# ジョブDBに "Creating xml file(s)"と送る
def send_condition(db_path, job_id):
    conn = sqlite3.connect(db_path, timeout=30.0)
    
    # WALモードの有効化（接続直後に1回実行すればOKですが、毎回呼んでも害はありません）
    # これにより「読み込み」と「書き込み」が同時にできるようになります
    conn.execute('PRAGMA journal_mode=WAL;')
    
    cursor = conn.cursor()
    status = ('Creating xml file(s)', job_id)

    try:
        cursor.execute('UPDATE job SET status = ? WHERE job_id = ?', status)
        conn.commit()
        logging.info("[!]  Updated Job Condition -> Creating xml file(s)")
    except Exception as e:
        error_msg = f"{e}(S1, send_condition)"
        ERROR_main(db_path, job_id, error_msg, g_cadno)
        return None 
    finally:
        conn.close()

# Innovator DBへの接続を確立し、接続オブジェクトを返す
def get_connection(db_config, job_id, job_db):
    try:
        conn_str = (
        f"DRIVER={{{db_config['DRIVER']}}};"
        f"SERVER={db_config['SERVER']};"
        f"DATABASE={db_config['DATABASE']};"
        f"UID={db_config['UID']};"
        f"PWD={db_config['PWD']};"
        f"TrustServerCertificate=yes;"
    )
        conn = pyodbc.connect(conn_str)
        return conn

    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        if sqlstate == 'IM002':
            error_msg = (
                "Connection Error",
                f"[ODBC Driver 18 for SQL Server] not found.\n"
                "Please Install it."
            )
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
            
        else:
            error_msg = (
                "Error",
                f"Failed to Connect to the Database.(S1)"
            )
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        return None

# Innovatorのユーザーであるか + アクティブユーザーであるかの確認
def get_inv_id(cursor, kz_number: str, job_db, job_id):
    inquiry_sql = """
    SELECT OWNED_BY_ID
    FROM [innovator].[USER] 
    WHERE LOGIN_NAME = ? AND LOGON_ENABLED = 1;
    """
    try:
        # ? にはkz番号が代入される。
        cursor.execute(inquiry_sql , kz_number)
        
        # 実行結果から1行だけ取得する
        result = cursor.fetchone()
        
        if result:
            owned_by_id = result[0]
            login_flag = True
            return login_flag, owned_by_id
        else:
            login_flag = False
            error_msg = f"{kz_number} not found or not active"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
            return login_flag, None
            
    except pyodbc.Error as e:
        login_flag = False
        error_msg = f"{e}(S1, get_inv_id)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        return login_flag, None
    
# ------------------------------------------
# リスト1: CNの公開先・ユーザー所属のグループID
# ------------------------------------------
# S2_Security.py で使用予定

# リスト1 を作成するための準備 ↓↓↓↓↓↓↓↓↓↓

def get_user_permission_ids(cursor, own_id: str) -> list:
    """
    指定されたユーザーIDを基に、所属する全ての親グループIDを再帰的に取得する。
    Args:
        cursor: 実行に使用するデータベースカーソル。
        user_id: 検索の起点となるユーザーのOWNED_BY_ID
    Returns:
        ユーザーが所属するグループ(KZW_ALL, RD_ALL...)
    """
    inquiry_sql = """
        WITH UserGroups (GroupID, Level) AS (
            SELECT SOURCE_ID, 0 AS Level 
            FROM [innovator].[MEMBER] WHERE RELATED_ID = ?
            UNION ALL
            SELECT m.SOURCE_ID, ug.Level + 1
            FROM [innovator].[MEMBER] m
            INNER JOIN UserGroups ug ON m.RELATED_ID = ug.GroupID
            WHERE ug.Level < 20
        )
        SELECT DISTINCT GroupID FROM UserGroups
        UNION
        SELECT ?;
    """
    cursor.execute(inquiry_sql, (own_id, own_id))
    return [row[0] for row in cursor.fetchall()]


def get_managed_by_id(job_db, job_id, cursor: pyodbc.Cursor, CN_NAME: str) -> str | None:
    """
    C/N(KEYED_NAME)を検索して、改訂するCNの公開先(MANAGED_BY_ID)を取得する。

    Args:
        cursor: 実行に使用するデータベースカーソル
        part_number: C/N番号EYED_NAME)

    Returns:
        公開先のMANAGED_BY_ID
    """
    inquiry_sql = """
        SELECT 
            MANAGED_BY_ID
        FROM
            [innovator].PART
        WHERE
            KEYED_NAME = ? AND IS_CURRENT = 1;
    """
    try:
        # SQLを実行。? には part_number が安全に代入される。
        cursor.execute(inquiry_sql, CN_NAME)
        
        # 実行結果から1行だけ取得する
        result = cursor.fetchone()
        
        if result:
            managed_by_id = result[0]
            return managed_by_id
        else:
            # 部品が見つからなかった場合
            error_msg = f"CN: '{CN_NAME}'  not found.(S1)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
            return None
            
    except pyodbc.Error as e:
        error_msg = f"{e}(S1, get_managed_by_id)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
        return None

#リスト1 を作成するための準備終わり ↑↑↑↑↑↑↑↑↑↑↑↑


# リスト1を作成する
# 辞書形式：{'cn_mid': ..., 'user_oid': ...}
# cn_mid  : cnの公開先 (MANAGED_BY_ID)
# user_oid: ユーザーが所属しているグループ (OWNED_BY_ID)

def get_list_1(job_db, job_id, cursor: pyodbc.Cursor, cn_name: str, own_id) -> dict | None:
    # 1. C/N(部品)の公開先(MANAGED_BY_ID)を取得
    managed_by_id = get_managed_by_id(job_db, job_id, cursor, cn_name)
    
    # 2. 公開先が見つからなかった場合、処理を中断してNoneを返す
    if not managed_by_id:
        return None
        
    # 3. ユーザーが所属するグループIDのリストを取得
    permission_ids = get_user_permission_ids(cursor, own_id)
    
    # 4. 取得した2つの情報を辞書にまとめる
    result_dict = {
        "cn_mid": managed_by_id,
        "user_oid": permission_ids
    }
    
    # 5. 完成した辞書を返す
    return result_dict

# CNにユーザーに公開されているかを確認
def security_check(permission_data: dict) -> bool:
    if not permission_data:
        return False

    cn_mid = permission_data.get('cn_mid')
    user_oid_list = permission_data.get('user_oid', [])

    # cn_mid が user_oid_list の中に存在するかを判定し、その結果(True/False)を返す
    return cn_mid in user_oid_list

# ------------------------------------------
# リスト2:  CATIAファイルのFILE ID
# 　　　    CATPrductのファイル名
# ------------------------------------------
# S3_get_native_cat.py で使用予定

def get_list_2(job_db, job_id, cursor, cn):
    inquiry_sql = """
        -- CADの階層構造を再帰的に検索するための共通テーブル式（CTE）を定義
        WITH CadHierarchy (ID) AS (
            -- 最初のCAD部品IDを取得する【再帰の起点】
            SELECT
                pcad.RELATED_ID
            FROM
                [innovator].PART p
            INNER JOIN
                [innovator].PART_CAD pcad ON p.ID = pcad.SOURCE_ID
            WHERE
                p.KEYED_NAME = ? AND p.IS_CURRENT = 1

            UNION ALL

            -- 見つかったCAD部品の子部品を再帰的に検索する【再帰部分】
            SELECT
                cs.RELATED_ID
            FROM
                [innovator].CAD_STRUCTURE cs
            INNER JOIN
                CadHierarchy ch ON cs.SOURCE_ID = ch.ID -- 前のステップで見つかったIDを次の検索キーにする
        )
        -- CTEで見つかったすべてのCAD部品IDを使って、最終的な情報を取得する
        SELECT DISTINCT
            f.FILENAME, 
            f.ID
        FROM
            [innovator].CAD c
        INNER JOIN
            CadHierarchy ch_final ON c.ID = ch_final.ID
        INNER JOIN
            [innovator].[FILE] f ON c.NATIVE_FILE = f.ID
    """
        # WHERE
        #     f.FILENAME NOT LIKE '%.CATPart%'
        # WHERE
        #     c.KEYED_NAME NOT LIKE '%DRS%';
    try:
        # SQLを実行。? には part_number が安全に代入される。
        cursor.execute(inquiry_sql, cn)
        #columns = [column[0] for column in cursor.description]
        results_list = cursor.fetchall()
        #results_list = [dict(zip(columns, row)) for row in rows]
        return results_list

    except pyodbc.Error as e:
        error_msg = f"{e}(S1, get_list_2)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)


# -------------------------------------------
# リスト3-1:  社内型式番号/パーツ名/
#            オーソリティ/製品種別コード
# -------------------------------------------
# S3_create_xml.pyで使用予定

def get_list_3_1(job_db, job_id, cursor, cn):
    #  get_list_3_1-1
    inquiry_sql = """
        SELECT
            P.NAME,
            P.INT_PARTNAME,
            P.DRAWING_TYPE
        FROM
            [innovator].PART AS P
        WHERE
            P.ITEM_NUMBER = ?
            AND P.IS_CURRENT = 1;
        """
    try:
        # SQLを実行。? には part_number が安全に代入される。
        cursor.execute(inquiry_sql, cn)
        # 結果をリストとして返す
        p_result = cursor.fetchall()

    except pyodbc.Error as e:
        error_msg = f"{e}(S1, get_list_3_1-1)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

    # 子部品図の場合：トップアッセンブリーを探す
    # get_list_3_1-2
    if cn and cn[0] != 'F':
        top_id_sql = """
            WITH 
            BOM_Climb AS (
                -- 1. アンカーメンバー: 入力された ITEM_NUMBER の ID
                -- (これが Level 1 となる)
                SELECT
                    P.ID AS CurrentPartID,
                    1 AS Level
                FROM
                    [innovator].PART AS P
                WHERE
                    P.ITEM_NUMBER = ? -- 1. 入力
                    AND P.IS_CURRENT = 1
                
                UNION ALL
                
                -- 2. 再帰メンバー: BOM を遡る
                SELECT
                    P_Parent.ID AS CurrentPartID, -- 見つかった親部品のID
                    prev.Level + 1                -- 階層レベルをインクリメント
                FROM
                    [innovator].PART_BOM AS bom
                JOIN
                    BOM_Climb AS prev ON bom.RELATED_ID = prev.CurrentPartID -- 現在の部品ID(prev)を子としてBOMを検索
                JOIN
                    [innovator].PART AS P_Parent ON bom.SOURCE_ID = P_Parent.ID -- BOMの親(SOURCE_ID)のPART情報を取得
                WHERE
                    prev.Level < 20             -- 再帰の上限を20回に設定
                    AND P_Parent.IS_CURRENT = 1   -- 親部品も IS_CURRENT = 1 であること
            ),

            RootPartIDs AS (
                -- 3. 最終的な親ID (n個のID) を特定
                -- (BOM_Climbの結果のうち、自分がRELATED_IDとして使われていないID = 最上位)
                SELECT DISTINCT
                    T1.CurrentPartID
                FROM
                    BOM_Climb AS T1
                LEFT JOIN
                    [innovator].PART_BOM AS PB_Check ON T1.CurrentPartID = PB_Check.RELATED_ID
                WHERE
                    PB_Check.RELATED_ID IS NULL -- これ以上親がいない (自分が子として使われていない)
            )

            -- 4. 最終結果の出力
            -- 最終的にたどり着いた 'n' 個の親部品について、ID と KEYED_NAME を取得
            SELECT
                P.KEYED_NAME
            FROM
                RootPartIDs AS RP
            JOIN 
                [innovator].PART AS P ON RP.CurrentPartID = P.ID
            -- (BOM_Climbの段階で IS_CURRENT = 1 はチェック済みだが、
            --  アンカーメンバー(Level 1)が最上位だった場合も考慮し、
            --  ここで PART 情報を JOIN して出力する)

            OPTION (MAXRECURSION 20);
        """
        try:
            # SQLを実行。? には part_number が安全に代入される。
            cursor.execute(top_id_sql, cn)
            # 結果をリストとして返す
            top_cns = cursor.fetchall()

        except pyodbc.Error as e:
            error_msg = f"{e}(S1, get_list_3_1-2)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

    # 製品図・子部品図共通
    # PRODUCT CLASS CODEを取得
    # get_list_3_1-3
    inquiry_sql = """
        SELECT
            OPP2.PRODUCT_TYPE
        FROM
            [innovator].PART AS P
        JOIN
            [innovator].ORG_PART_PARTATTR_PRODUCT AS OPP1 ON P.ID = OPP1.SOURCE_ID
        JOIN
            [innovator].ORG_PARTATTR_PRODUCT AS OPP2 ON OPP1.RELATED_ID = OPP2.ID
        WHERE
            P.ITEM_NUMBER = ?
            AND P.IS_CURRENT = 1;
    """
    try:
        # SQLを実行。? には part_number が安全に代入される。
        # 製品図の場合 (cnとproduct class code は一対一対応)
        if cn and cn[0] == 'F':
            cursor.execute(inquiry_sql, cn)
            f_pcc = cursor.fetchall()
            result = [tuple(p_result[0]) + tuple(f_pcc[0])]
            return result
        else:
            pccs = []
            if top_cns == None:
                c_pcc = "A"
                result = [tuple(p_result[0]) + tuple(c_pcc[0])]
                return result
            for cn in top_cns:
                if not cn[0].startswith("F"):
                    continue    
                cursor.execute(inquiry_sql, cn)
                c_pcc = cursor.fetchall()
                pccs.append(c_pcc[0])

            pccs = [item[0] for item in pccs]

            if pccs == []:
                c_pcc = "A"
                result = [tuple(p_result[0]) + tuple(c_pcc[0])]
                return result

            # product class code が厳しいものを採用するプログラム
            if "AA" in pccs:
                c_pcc = "AA"
                result = [tuple(p_result[0]) + tuple(c_pcc[0])]
                return result

            elif "A" in pccs:
                c_pcc = "A"
                result = [tuple(p_result[0]) + tuple(c_pcc[0])]

                return result

            elif "J" in pccs:
                c_pcc = "J"
                result = [tuple(p_result[0]) + tuple(c_pcc[0])]
                return result

            else:
                c_pcc = "C"
                result = [tuple(p_result[0]) + tuple(c_pcc[0])]
                return result

    except pyodbc.Error as e:
        error_msg = f"{e}(S1, get_list_3_1-3)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)


# ------------------------------------------
# リスト3-2:  SUBSQ(e.g. PA010, STOCK...)
# 　　　      作成者/検図者/承認者 
# 　　　      日付/REV/CAD doc.のID
#  ------------------------------------------

# S4_create_xml.pyで使用予定
# PAごとに異なるため、リストを分けている

# 検図者の名前や日付、REVはDRSをもとに反映する
def get_list_3_2(job_db, job_id, cursor, cn, user_id):
    inquiry_sql = """
    WITH CadHierarchy (ID, RootKeyedName) AS (
        -- 【初期クエリ】最初のCAD部品を取得し、ROOTの名称を保持する
        SELECT
            pcad.RELATED_ID,
            p.KEYED_NAME -- ここで最初の部品番号を保持
        FROM
            [innovator].PART p
        INNER JOIN
            [innovator].PART_CAD pcad ON p.ID = pcad.SOURCE_ID
        WHERE
            p.KEYED_NAME = ? AND p.IS_CURRENT = 1

        UNION ALL

        -- 【再帰クエリ】子部品を検索し、RootKeyedNameを引き継ぐ
        SELECT
            cs.RELATED_ID,
            ch.RootKeyedName
        FROM
            [innovator].CAD_STRUCTURE cs
        INNER JOIN
            CadHierarchy ch ON cs.SOURCE_ID = ch.ID
    )
    -- 最終的な情報取得
    SELECT DISTINCT
        c.KEYED_NAME,
        (
            SELECT TOP 1 u.KEYED_NAME 
            FROM [innovator].[USER] u 
            WHERE u.LOGIN_NAME = ? AND u.LOGON_ENABLED = 1
        ) AS CREATED_BY_NAME,

        checker.KEYED_NAME  AS CHECK_BY_NAME, 
        approver.KEYED_NAME AS APPROVAL_BY_NAME,
        c.MODIFIED_ON,
        c.CHECK_ON,
        c.APPROVAL_ON,
        c.MAJOR_REV,
        c.ID
    FROM
        [innovator].CAD c
    INNER JOIN
        CadHierarchy ch_final ON c.ID = ch_final.ID
    LEFT JOIN
        [innovator].[USER] checker ON c.CHECK_BY_ID = checker.CONFIG_ID
    LEFT JOIN
        [innovator].[USER] approver ON c.APPROVAL_BY_ID = approver.CONFIG_ID
    WHERE
        -- アンダーバーの数によるフィルタリング
        (LEN(c.KEYED_NAME) - LEN(REPLACE(c.KEYED_NAME, '_', ''))) < 2
        -- 【修正】c.KEYED_NAMEが、最初に指定したRootKeyedNameで始まるもののみ
        AND c.KEYED_NAME LIKE ch_final.RootKeyedName + '%';
    """
    try:
        # SQLを実行。? には part_number が安全に代入される。
        cursor.execute(inquiry_sql, cn, user_id)
        # 結果をリストとして返す
        result = cursor.fetchall()

        # アルファベット順にソートする
        # DRS01, PA010, PA020..., STOCKの順になる
        sorted_result = sorted(result)

        return sorted_result

    except pyodbc.Error as e:
        error_msg = f"{e}(S1, get_list_3_2)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

# ------------------------------------------
# リスト3-3:  SUBSQ(e.g. PA010, STOCK...)
# 　　　      DCN/ECN
#  ------------------------------------------
# S4_create_xml.pyで使用予定

# DCN/ECNはDRSのフォームによってのみ記載する
def get_list_3_3(cursor, cn):
    inquiry_sql = """
        WITH DRSCAD (ID) AS (
            SELECT DISTINCT
                cad.ID
            FROM
                [innovator].PART p
            INNER JOIN
                [innovator].PART_CAD pcad ON p.ID = pcad.SOURCE_ID
            INNER JOIN
                [innovator].CAD cad ON cad.ID = pcad.RELATED_ID
            WHERE
                p.KEYED_NAME = ? AND p.IS_CURRENT = 1
        )
        SELECT DISTINCT
            T3.KEYED_NAME,
            T2.SORT_ORDER
        FROM
            DRSCAD AS T1
        INNER JOIN
            [Innovator].[ORG_CAD_DCN_RD] AS T2 ON T1.ID = T2.SOURCE_ID
        INNER JOIN
            [Innovator].[ORG_DCN_RD] AS T3 ON T3.ID = T2.RELATED_ID;
    """

    cursor.execute(inquiry_sql, cn)
    result = cursor.fetchall()
    #logging.info(f"list_3_3: {result}")
    
    if not result:
        # 結果が空（0件）の場合は、['---'] を辞書に追加
        result = ['---']
    return result

# --------------------------------------
# リスト4: SHEET(PA010)/工程順/工程コード/
#          工程名(EN)/工程注記
#  -------------------------------------
# S4_create_xml.pyで使用予定

def get_list_4(job_db, job_id, cursor, cn):
    inquiry_sql = """
        SELECT
            PS.SHEET,
            PS.PROCESS_SEQNO,
            PI.PROCESS_CODE,
            PI.PROCESS_NAME_EN,
            PS.DESCRIPTION
        FROM
            [INNOVATOR].[PART] AS P
        INNER JOIN
            [INNOVATOR].[PART_PROCESSPLAN] AS PP ON P.ID = PP.SOURCE_ID
        INNER JOIN
            [INNOVATOR].[ORG_PROCESSPLAN_RD] AS OPR ON PP.RELATED_ID = OPR.ID
        INNER JOIN
            [INNOVATOR].[ORG_PROCESSPLAN_PROSEQ_RD] AS OPPR ON OPR.ID = OPPR.SOURCE_ID
        INNER JOIN
            [INNOVATOR].[ORG_PROCESSSEQUENCE_RD] AS PS ON OPPR.RELATED_ID = PS.ID
        LEFT JOIN
            [INNOVATOR].[ORG_PROCESS_RD] AS PI ON PS.PROCESS_CODE = PI.ID
        WHERE
            P.KEYED_NAME = ? -- ここに対象のPART番号を指定
            AND P.IS_CURRENT = 1
            AND PS.IS_CURRENT = 1;
    """

    try:
        # SQLを実行。? には part_number が安全に代入される。
        cursor.execute(inquiry_sql, cn)
        # 結果をリストとして返す
        rows = cursor.fetchall()
        converted_list = []
        
        # 通常通りリストを返すと、工程順がDecimal('9')のように表示される
        # intに変換して、converted_listとして結果を返す
        for row in rows:
            #logging.info(row.SHEET)
            if row.SHEET == "VAGUE": # b.工程情報> "SHEET"が正しく入力されていない場合はエラー
                error_msg = f"Innovator > b.Process Information> \"Sheet\" is \"VAGUE\".(S1)"
                ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

            # 2番目の要素(インデックス1)をintに変換
            process_seqno_int = int(row.PROCESS_SEQNO) # もしくは int(row[1])
            #description_text = row.DESCRIPTION if row.DESCRIPTION else "N/A"
            
            # 変換後の値を使って新しいタプルを作成
            converted_row = (
                row.SHEET,               # row[0]
                process_seqno_int,       # ★変換した値
                row.PROCESS_CODE,        # row[2]
                row.PROCESS_NAME_EN,     # row[3]
                row.DESCRIPTION          # row[4]
            )
            
            # 新しいリストに追加
            converted_list.append(converted_row)
            # print(row.PROCESS_CODE)
            # print(row.DESCRIPTION )
            # print("------------------------")
            
        return converted_list

    except pyodbc.Error as e:
        error_msg = f"{e}(S1, get_list_4)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)


g_cadno = None
g_user_id = None
def S1_main(job_db, job_id, cn, user_id, cadno):

    list_1 = list_2 = list_3_1 = list_3_2 = list_3_3 = list_4 = None
    
    send_condition(job_db, job_id)

    # cadnoをグローバル変数に保存
    global g_cadno
    global g_user_id

    g_cadno = cadno
    g_user_id = user_id

    # InnovatorDB 接続
    conn = get_connection(DB_CONFIG, job_id, job_db)
    cursor = conn.cursor()

    try:
        #print("login")

        login_flag, owned_by_id = get_inv_id(cursor, user_id, job_db, job_id)

        if login_flag == False: # 登録されていない場合はプログラムを終了。この先のプログラムにも進めない。
            conn.close()
            sys.exit(1)
        
        list_1 = get_list_1(job_db, job_id, cursor, cn, owned_by_id)
        #print(list_1)
        if security_check(list_1):
            pass
        else:
            error_msg = f"USER: '{user_id}' have no access to CN: '{cn}'.(S1)"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

        # CADネイティブファイル
        list_2 = get_list_2(job_db, job_id, cursor, cn)

        if not list_2:
            error_msg = f"CAD native file missing. Verify CAD Nativefile upload or Part-CAD relation"
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)


        # 社内型式名など
        list_3_1 = get_list_3_1(job_db, job_id, cursor, cn)

        if not list_3_1:
            error_msg = f"Part infomation is Empty."
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

        # 作成者・検図者などの情報
        list_3_2 = get_list_3_2(job_db, job_id, cursor, cn, user_id)

        list_3_3 = get_list_3_3(cursor, cn)
        


        # 工程注記
        list_4 = get_list_4(job_db, job_id, cursor, cn)
        if not list_4:
            error_msg = f"Process info is Empty."
            ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

        return list_1, list_2, list_3_1, list_3_2, list_3_3, list_4

    finally:
        conn.close()
        logging.info('Closed INV DB')