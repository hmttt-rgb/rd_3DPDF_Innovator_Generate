"""
job管理DBにjobの登録
"""
import os
import random
import string
import sqlite3


# job_id を決める
def generate_job_id(length):
    """指定された長さのランダムな英数字IDを生成する (例: 'A5T10B7X')"""
    # 使用する文字 (アルファベット大文字 + 数字)
    chars = string.ascii_uppercase + string.digits
    # 指定された長さのランダムな文字列を生成
    return ''.join(random.choices(chars, k=length))

def create_and_insert_job(db_path, user_id, cn_value):
    # 1. job_idを作成
    new_id = generate_job_id(8)

    # 2. データベースに接続してデータを挿入
    #print(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO job (userid, job_id, cn) VALUES (?, ?, ?)",
            (user_id, new_id, cn_value) # 取得したcn_valueを使用
        )
        conn.commit()

        #print("Created JOB ID")
        return new_id
    except Exception as e:
        print(f"ERROR: {e}")
        return None 
    finally:
        conn.close()