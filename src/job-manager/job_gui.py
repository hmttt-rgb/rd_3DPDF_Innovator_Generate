
import sys
import json

import urllib.request
import urllib.parse
import urllib.error

import datetime # datetimeのインポートを追加

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QMessageBox 
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QObject, QTimer
from PyQt6.QtGui import QColor

# --- 設定 ---
# 本番
from dotenv import load_dotenv
load_dotenv()
API_URL = os.getenv("API_URL")
VALID_API_KEY = os.getenv("VALID_API_KEY")


# --- 1. API通信を別スレッドで行うためのWorkerクラス ---
class JobFetcher(QObject):
    """APIからジョブデータを取得する処理を別スレッドで行うためのWorker"""
    # 処理結果をメインスレッドに送るためのシグナルを定義
    finished = pyqtSignal(object) # 成功時にデータ(jobs)を送る
    error = pyqtSignal(str)      # 失敗時にエラーメッセージを送る

    def run(self):
        """スレッドが実行するメイン処理 (API通信)"""
        try:
            params = {
                'key_gui': VALID_API_KEY,
                'cn': '',       
            }
            
            # 1. パラメータをURLエンコードする
            query_string = urllib.parse.urlencode(params)
            
            # 2. URLと結合する ('?' の有無で処理を分ける)
            if '?' in API_URL:
                full_url = f"{API_URL}&{query_string}"
            else:
                full_url = f"{API_URL}?{query_string}"
            
            # 3. リクエストオブジェクトを作成
            req = urllib.request.Request(full_url)
            
            # 4. urlopen で通信する
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read()
                jobs = json.loads(body.decode('utf-8'))
            
            # 成功した場合、データをシグナルでメインスレッドに送信
            self.finished.emit(jobs)
            
        except urllib.error.HTTPError as e:
            error_msg = f"API HTTPエラー ({e.response.status_code}): {e.response.text}"
            self.error.emit(error_msg)
        except urllib.error.URLError as e:
            error_msg = f"API接続エラー: {e}"
            self.error.emit(error_msg)
        except json.JSONDecodeError:
            error_msg = "API応答のJSON形式が不正です。"
            self.error.emit(error_msg)
        except Exception as e:
            error_msg = f"予期せぬエラー: {type(e).__name__}: {e}"
            self.error.emit(error_msg)


class JobManagerWindow(QMainWindow):
    """
    3DPDF生成ジョブのステータスを表示・管理するGUIウィンドウ
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3DPDF Job Manager")
        self.setGeometry(100, 100, 1000, 600)
        
        self.worker_thread = None # QThreadインスタンスを保持
        self.all_jobs = []        # 全ジョブデータを保持する変数
        self.is_fetching = False  # データ取得中フラグ
        
        # リフレッシュボタンのクールダウン用タイマー
        self.refresh_cooldown_timer = QTimer()
        self.refresh_cooldown_timer.timeout.connect(self.enable_refresh_button)
        self.refresh_cooldown_remaining = 0  # クールダウン残り時間
        
        self._setup_ui()
        
        # 初回データ取得を実行
        self.start_fetch()
        

    def _setup_ui(self):
        """UIの部品をセットアップし、レイアウトに配置する"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        header_layout = QHBoxLayout()
        
        title_label = QLabel("3DPDF Job Manager")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search CN...")
        self.search_input.setFixedWidth(200)
        self.search_input.returnPressed.connect(self.apply_filter)
        
        self.search_button = QPushButton("🔍 Search")
        self.search_button.setFixedWidth(100) 
        self.search_button.clicked.connect(self.apply_filter)
        
        # リフレッシュボタンの動作を非同期処理の開始に変更
        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.setFixedWidth(100)
        self.refresh_button.clicked.connect(self.start_fetch) 
        
        header_layout.addWidget(title_label)
        header_layout.addStretch(1) 
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(self.search_input)
        header_layout.addWidget(self.search_button)
        main_layout.addLayout(header_layout)

        self.job_table = QTableWidget()
        self.job_table.setColumnCount(5)
        self.job_table.setHorizontalHeaderLabels(['Date(JST)', 'CN', 'Status', 'Condition', 'Error'])
        self.job_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_layout.addWidget(self.job_table)
        
        self.status_bar_label = QLabel("Last Update: ---")
        self.status_bar_label.setWordWrap(True)
        main_layout.addWidget(self.status_bar_label)


    def start_fetch(self):
        """API通信を新しいスレッドで開始する"""
        if self.is_fetching:
            self.status_bar_label.setText("⚠️ Retrieving Job Data. Please Wait...")
            return

        self.is_fetching = True
        self.refresh_button.setText("Loading...")
        self.refresh_button.setEnabled(False)
        self.status_bar_label.setText("Retrieving Job Data from the API...")
        
        # クールダウンを開始（5秒間ボタンを無効化）
        self.refresh_cooldown_remaining = 5
        self.refresh_cooldown_timer.start(1000)  # 1秒ごとにタイムアウト
        
        # QThreadとWorkerを初期化
        self.worker_thread = QThread()
        self.worker = JobFetcher()
        self.worker.moveToThread(self.worker_thread)
        
        # シグナルとスロットの接続
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_fetch_success)
        self.worker.error.connect(self.on_fetch_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.cleanup_thread)

        # スレッド開始
        self.worker_thread.start()


    def on_fetch_success(self, jobs):
        """データ取得成功時にメインスレッドで実行される処理"""
        self.all_jobs = jobs # 全ジョブを保存
        self.apply_filter()  # 現在の検索フィルタを適用
        
        # 最終更新日時をステータスバーに表示
        self.status_bar_label.setText(f"Last Update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


    def on_fetch_error(self, error_msg):
        """データ取得失敗時にメインスレッドで実行される処理"""
        # 1. ポップアップを表示
        QMessageBox.warning(
            self,
            "API Connection Error",
            f"An Error Occurred while getting Job Data. \n\nDetail: {error_msg}",
            QMessageBox.StandardButton.Ok
        )
        
        # 2. ステータスバーに表示
        self.status_bar_label.setText(f"Error: {error_msg}")

        # 3. コンソールに出力 (デバッグ用)
        print(error_msg)


    def cleanup_thread(self):
        """スレッド終了後の後処理"""
        self.worker.deleteLater()
        self.worker_thread.deleteLater()
        self.worker_thread = None
        self.worker = None
        self.is_fetching = False
        self.refresh_button.setText("🔄 Refresh")
        self.refresh_button.setEnabled(True)

    def enable_refresh_button(self):
        """クールダウン中はボタンを無効化し、テキストに残り時間を表示"""
        self.refresh_cooldown_remaining -= 1
        
        if self.refresh_cooldown_remaining > 0:
            # まだクールダウン中：ボタンを暗くする（テキストは変えない）
            self.refresh_button.setEnabled(False)
            self.refresh_button.setStyleSheet("background-color: #d3d3d3; color: #666666;")
        else:
            # クールダウン完了：ボタンを再度有効化
            self.refresh_button.setEnabled(True)
            self.refresh_button.setStyleSheet("")  # デフォルトスタイルに戻す
            self.refresh_cooldown_timer.stop()


    def apply_filter(self):
        """検索入力に基づいてジョブデータをフィルタリングし、テーブルを更新する"""
        search_term = self.search_input.text().lower().strip()
        
        if not search_term:
            filtered_jobs = self.all_jobs
        else:
            filtered_jobs = [
                job for job in self.all_jobs 
                if search_term in job.get('cn', '').lower()
            ]

        self._update_table(filtered_jobs)


    def _update_table(self, jobs):
        """受信したデータでテーブルを更新する"""
        self.job_table.setRowCount(len(jobs))
        
        # JST (UTC+9) のタイムゾーン定義
        JST = datetime.timezone(datetime.timedelta(hours=9))

        for row_index, job in enumerate(jobs):
            # jobオブジェクトがNoneでないことを確認
            if job is None:
                # printとステータスバーに警告を表示
                print(f"Warning: Job is Empty")
                self.status_bar_label.setText("Waring: Data Issue Detected.")
                continue
                
            # --- 日付変換処理 (DateはUTCをJSTに変換) ---
            date_utc_str = job.get('date', '---')
            date_jst_str = date_utc_str
            
            if date_utc_str != '---':
                try:
                    # データベースから取得したUTC文字列をdatetimeオブジェクトとして解析
                    # 例: "2024-01-01 10:00:00" 形式を想定
                    dt_utc_naive = datetime.datetime.strptime(date_utc_str, '%Y-%m-%d %H:%M:%S')
                    # NaiveなdatetimeオブジェクトにUTCのタイムゾーン情報を付与 (awareにする)
                    dt_utc_aware = dt_utc_naive.replace(tzinfo=datetime.timezone.utc)
                    
                    # JST (UTC+9) に変換
                    dt_jst = dt_utc_aware.astimezone(JST)
                    
                    # 表示用にフォーマット
                    date_jst_str = dt_jst.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    date_jst_str = f"Date Parse Error: {date_utc_str}"
                except Exception as e:
                    date_jst_str = f"Date Error: {e}"
            # ---------------------------------------------
                
            # APIから返されるキー名と表示順序を合わせる: date, cn, status, condition, error
            data_columns = [
                date_jst_str, # 変換後のJST文字列を使用
                job.get('cn', '---'), 
                job.get('status', '---'), 
                job.get('condition', '---'), 
                job.get('error', '---')
            ]
            
            for col_index, data in enumerate(data_columns):
                item_data = str(data) if data is not None else 'N/A'
                item = QTableWidgetItem(item_data)
                
                # --- ステータスとコンディションに応じた色分けロジック ---
                
                status_raw = job.get('status', '')
                status = str(status_raw).lower() if status_raw is not None else ''

                condition_raw = job.get('condition', '')
                condition = str(condition_raw).lower() if condition_raw is not None else ''

                # 1. Status (3列目, index=2) の色分け
                if col_index == 2: # 'Status'列
                    if 'complete' in status:
                        item.setBackground(QColor(200, 255, 200)) # 薄い緑 (Completed)
                    elif 'running' in status:
                        item.setBackground(QColor(255, 255, 200)) # 薄い黄 (Running)

                # 2. Condition (4列目, index=3) の色分け (Failed/Cancel対応)
                elif col_index == 3: # 'Condition'列
                    if 'failed' in condition:
                        item.setBackground(QColor(255, 180, 180)) # 赤 (Failed)
                    elif 'cancel' in condition:
                        item.setBackground(QColor(255, 255, 180)) # 黄 (Cancel)
                    
                
                if col_index == 4:  # Error列
                    # 左寄せ + 垂直方向は中央
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                else:
                    # 中央揃え
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                self.job_table.setItem(row_index, col_index, item)
        
        # テーブルの列幅をコンテンツに合わせて調整
        self.job_table.resizeColumnsToContents()
        self.job_table.horizontalHeader().setStretchLastSection(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = JobManagerWindow()
    main_window.show()
    sys.exit(app.exec())