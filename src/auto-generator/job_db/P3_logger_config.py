import datetime
import logging
import sys
import os

def setup_logger(cadno):
    """
    ロガーを設定し、ファイルとコンソールに同時に出力する関数。
    """
    # フォーマッターの作成
    formatter = logging.Formatter('%(asctime)s | %(module)s, %(lineno)d |:  %(message)s', datefmt='%H:%M:%S')
    
    # ロガーの取得
    logger = logging.getLogger() # ルートロガーを取得
    logger.setLevel(logging.INFO)
    
    # 既存のハンドラをクリア (重複設定を防ぐ)
    if logger.hasHandlers():
        logger.handlers.clear()

    # コンソール出力用のハンドラ
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # ファイル出力用のハンドラ (ファイルパス: C:\LOG)
    log_filepath = r"C:\3DPDF\21_LOG"

    # 日付時刻
    now = datetime.datetime.now()
    date_time_str = now.strftime('%Y%m%d_%H%M%S')
    
    # ログファイル名・パスの作成
    log_filename = f"_______{cadno}_{date_time_str}_3DPDF_Generate.log"
    log_fullpath = os.path.join(log_filepath, log_filename)

    file_handler = logging.FileHandler(log_fullpath, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger, log_fullpath