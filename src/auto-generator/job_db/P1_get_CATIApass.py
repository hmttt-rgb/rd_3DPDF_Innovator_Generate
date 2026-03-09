"""
cnとuserid(社員番号)を取得
"""

import sys

def get_info():
    cadno = sys.argv[1]     # 例: F01-02096_DRS01
    cn_value = cadno.split('_')[0] # 例: F01-02096 ("_"で分割した最初の要素を取得)

    userid = sys.argv[2]

    ver = sys.argv[3]     # CATIA図面のバージョン

    return cn_value, userid, cadno, ver