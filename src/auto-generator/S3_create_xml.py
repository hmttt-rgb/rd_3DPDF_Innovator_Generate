"""
図面v1.30用(加工情報DS対応)のxml生成
3DPDF生成時に必要なxmlを作成する
"""

import os
import logging
from datetime import datetime, timedelta
from ERROR import ERROR_main
import xml.etree.ElementTree as ET
import glob
import re
import shutil

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


def format_name(full_name: str) -> str:
    """ Haruka Matsuta -> H. Matsuta """
    try:
        first, last = full_name.split(' ', 1)
        return f"{first[0]}. {last}"
    except (ValueError, IndexError):
        # 空白がないなど、予期せぬ形式の場合は元の名前を返す
        return full_name


def create_single_xml(sheet, subsq, cn, list_3_1, list_3_2, list_3_3, list_4, xml_path, job_db, job_id, op, template_flag):
    """1つのシートに対応するXMLファイルを生成する共通関数"""
    
    # list_3_1 から基本情報を取得
    partno, partname, authority, productclass = list_3_1[0]

    # list_3_2 から承認者情報を検索
    approval_info = list_3_2[0]

    # 承認者情報が見つからない場合は処理をスキップ
    if not approval_info or None in approval_info:
        error_msg = "Creator, Checker, Approver, Date Information not Found. Please Register those Information in Innovator.(S3)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)

    # 基本情報整理
    creator  = format_name(approval_info[1])  # 作成者：最終更新者=作成者である前提
    checker  = format_name(approval_info[2])  # 検図者
    approver = format_name(approval_info[3])  # 承認者
    rev      = approval_info[7]               # リビジョン
    
    create_date   = datetime.now().strftime('%Y/%m/%d')                          # 今の日付
    check_date    = (approval_info[5] + timedelta(hours=9)).strftime('%Y/%m/%d')  # 検図日(DRSが基準)
    approval_date = (approval_info[6] + timedelta(hours=9)).strftime('%Y/%m/%d')  # 承認日(DRSが基準)
    
    # list_3_3 からDCN情報を取得
    # DCNが複数ある場合(list_3_3に複数含まれる場合)
    # 参考
    # list_3_3: [('DCN097242', 256), ('ECN001050', 128)]
    num_dcn = len(list_3_3)
    if num_dcn >= 2:
        sorted_dcn = sorted(list_3_3, key=lambda item: item[1])
        dcn = tuple(sorted_dcn[0])[0]
        more_docs = num_dcn -1
        dcnmore = f"+{more_docs} doc(s)"
    else:
        dcn = list_3_3[0]
        #logging.info(dcn)

    # list_4 から工程情報を取得し、文字列に結合
    # 該当sheet名の工程情報を取得　-> 工程順に並び変える
    process_info = sorted([row for row in list_4 if row[0] == sheet], key=lambda r: r[1])

    # 同じシート内に工程注記が存在するかどうかを確認
    is_any_note_present = any(row[4] and row[4].strip() for row in process_info)
    notes_parts = []

    if not is_any_note_present:
        # 同じsheet内の工程注記が無し -> 工程注記は "N/A"
        notes_parts.append("N/A")
        op = op + 1
    else:
        for row in process_info:
            op = op + 1

            body = row[4] # 工程注記

            # INV上に、注記が存在する場合のみ注記情報を記載する。
            if body and body.strip():

                pattern = r'(?=< ?(?:REQUIREMENT|客先要求))'
                if row[3] == "STOCK":
                    if body.lstrip().startswith(("<REQUIREMENT", "< REQUIREMENT", "<客先要求", "< 客先要求")): # STOCKの注記が無く、製品要求から始まる場合
                        notes_parts.append(body.strip()) 
                    else:
                        if re.search(pattern, body): # STOCKの注記がある + 製品要求もある場合
                            parts = re.split(pattern, body)
                            footer = "___________________________________________________________"
                            new_body = (footer).join(parts) # STOCKの注記と製品要求を区切る
                        
                            header = f"■#{row[2]} {row[3]}■"
                            notes_parts.append(header)
                            notes_parts.append(new_body)
                        else: # それ以外
                            header = f"■#{row[2]} {row[3]}■"
                            notes_parts.append(header)
                            notes_parts.append(body)

                else: # STOCK以外の図面
                    # ■を直接文字列に入れる
                    header = f"■#{row[2]} {row[3]}■"
                    footer = "___________________________________________________________"
                    
                    notes_parts.append(header)
                    notes_parts.append(body)
                    notes_parts.append(footer)

    # 全てのパーツを改行コード("\n")で結合する
    notes_str = "\n".join(notes_parts)
    #notes_str = "\r".join(notes_parts)

    root = ET.Element("Fields")
    if num_dcn >= 2:
        field_list = [
            # ここで、生の文字列 notes_str を value に設定する
            {'key': 'WI', 'value': notes_str},
            {'key': 'DWGNO', 'value': f"{cn}_DRS01"},
            {'key': 'SUBSQ', 'value': subsq},
            {'key': 'DWGREV', 'value': rev},
            {'key': 'PARTNO', 'value': partno},
            {'key': 'PARTNAME', 'value': partname},
            {'key': 'DCN', 'value': dcn},
            {'key': 'DCNMORE', 'value': dcnmore},
            {'key': 'DRAWN', 'value': creator},
            {'key': 'DRAWNDATE', 'value': create_date},
            {'key': 'CHECKER', 'value': checker},
            {'key': 'CHECKEDDATE', 'value': check_date},
            {'key': 'APPROVER', 'value': approver},
            {'key': 'APPROVEDDATE', 'value': approval_date},
            {'key': 'PRODUCTCLASSCODE', 'value': productclass},
            {'key': 'AUTHORITYDATA', 'value': authority},
        ]
    else:
        field_list = [
            # ここで、生の文字列 notes_str を value に設定する
            {'key': 'WI', 'value': notes_str},
            {'key': 'DWGNO', 'value': f"{cn}_DRS01"},
            {'key': 'SUBSQ', 'value': subsq},
            {'key': 'DWGREV', 'value': rev},
            {'key': 'PARTNO', 'value': partno},
            {'key': 'PARTNAME', 'value': partname},
            {'key': 'DCN', 'value': dcn},
            {'key': 'DRAWN', 'value': creator},
            {'key': 'DRAWNDATE', 'value': create_date},
            {'key': 'CHECKER', 'value': checker},
            {'key': 'CHECKEDDATE', 'value': check_date},
            {'key': 'APPROVER', 'value': approver},
            {'key': 'APPROVEDDATE', 'value': approval_date},
            {'key': 'PRODUCTCLASSCODE', 'value': productclass},
            {'key': 'AUTHORITYDATA', 'value': authority},
        ]

    # 全てのデータを属性として設定するシンプルなループ
    for attrs in field_list:
        ET.SubElement(root, "Field", attrib=attrs)

    tree = ET.ElementTree(root)

    xml_name = f"{cn}_{sheet}_Text_Field_Process.xml"
    path = os.path.join(xml_path, xml_name)
    ET.indent(tree)
    tree.write(path, encoding='utf-8', xml_declaration=True)

    # 工程注記が44行を超える場合は、フラグを立てて3DPDFのテンプレートファイルを差し替える
    line_count = len('\n'.join(notes_parts).splitlines())
    
    limit = 42
    is_over_limit = line_count > limit
    template_flag.append((sheet, is_over_limit))
    # print(f'Line Count: {line_count}')
    # print(f"{'\n'.join(notes_parts)}")
    
    return op, template_flag


def build_template_list_from_input(input_path):
    """
    Inputフォルダ内のXMLファイルから、各シートのWIフィールドの行数を読み取り、
    template_list (シート名, 42行超過フラグ) を生成する。
    """
    limit = 42
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


def make_xml(list_3_1, list_3_2, list_3_3, list_4, cn, xml_path, job_db, job_id, output_path):
    """PAシートとSTOCKシートのXMLを順番に生成する"""
    total_sheets = len(list_3_2) -1  # DRSは不要であるため -1 

    sheets = [f"PA{i:02}0" for i in range(1, total_sheets)] + ["STOCK"]

    template_flag = []

    org_op = 1
    for i, sheet in enumerate(sheets, 1):
        subsq = f"{sheet}({i}/{total_sheets})"
        op, template_list = create_single_xml(sheet, subsq, cn, list_3_1, list_3_2, list_3_3, list_4, xml_path, job_db, job_id, org_op, template_flag)
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

g_cadno = None
g_user_id = None
def S3_main(job_db, job_id, list_3_1, list_3_2, list_3_3, list_4, cn, cn_path, cadno, user_id):
    try:
        global g_cadno        
        global g_user_id
        g_cadno = cadno
        g_user_id = user_id

        xml_base_path = os.path.join(cn_path, "XML")
        os.makedirs(xml_base_path, exist_ok=True) 

        # コンピューターが読み取る用のXMLのパス
        xml_path = os.path.join(xml_base_path, "xml")
        if os.path.exists(xml_path):
            try:
                shutil.rmtree(xml_path)

            except Exception as e:
                print(f"Failed to delete folder: {e}")
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

            # inputファイル内の仕切り線を修正
            
            return template_list
        else:
            template_list = make_xml(list_3_1, list_3_2, list_3_3, list_4, cn, xml_path, job_db, job_id, output_timepath)
            logging.info("XML File(s) are Successfully Created !")
        return template_list

    except Exception as e:
        #messagebox.showerror("ERROR", f"{e}")
        error_msg = f"{e}(S3)"
        ERROR_main(job_db, job_id, error_msg, g_cadno, g_user_id)
