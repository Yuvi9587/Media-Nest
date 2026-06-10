import os
import sys
import sqlite3
import hashlib
import requests
import threading
import datetime
import imagehash
import time
import uuid
from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QGroupBox, QListWidget,
                             QFileDialog, QMessageBox, QCompleter, QListWidgetItem,
                             QSplitter, QSizePolicy, QApplication, QDialog,
                             QProgressBar, QRadioButton, QButtonGroup, QCheckBox,
                             QPlainTextEdit, QStackedWidget, QSlider)
from PyQt6.QtCore import Qt, QStringListModel, QThread, pyqtSignal, QSize, QUrl, QTimer, QSettings
from PyQt6.QtGui import QPixmap, QImageReader, QMovie, QIcon, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from Src.Logic.paths import resource_path
from Src.Logic.visual_sorter import VisualSorter

class ResponsiveImageLabel(QLabel):
    """A smart label that dynamically resizes images AND GIFs to fit any screen."""
    def __init__(self, text=""):
        super().__init__(text)
        self.setMinimumSize(100, 100)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #151515; border: 1px solid #454545; border-radius: 6px; padding: 5px;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pixmap = None
        self._movie = None

    def set_image(self, file_path):
        self.clear_image("")
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.gif':
            self._movie = QMovie(file_path)
            self.setMovie(self._movie)
            self._movie.start()
            self._scale_movie()
        else:
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)
                self.update_image_display()

    def clear_image(self, text=""):
        if self._movie:
            self._movie.stop()
            self.setMovie(None)
            self._movie = None
        self._pixmap = None
        self.setText(text)

    def update_image_display(self):
        if self._pixmap and not self._pixmap.isNull():
            scaled_pixmap = self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled_pixmap)

    def _scale_movie(self):
        if self._movie and self._movie.isValid():
            orig_size = self._movie.currentImage().size()
            if not orig_size.isEmpty():
                scaled_size = orig_size.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
                self._movie.setScaledSize(scaled_size)

    def resizeEvent(self, event):
        if self._pixmap:
            self.update_image_display()
        elif self._movie:
            self._scale_movie()
        super().resizeEvent(event)

class SafeJumpSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
            event.accept()
        super().mousePressEvent(event)

class UniversalMediaViewer(QWidget):
    def __init__(self, default_text="Select a file from the Inbox to work on", parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)

        self.image_label = ResponsiveImageLabel(default_text)
        self.stack.addWidget(self.image_label)

        self.video_container = QWidget()
        self.video_layout = QVBoxLayout(self.video_container)
        self.video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_layout.setSpacing(5)

        self.video_widget = QVideoWidget()
        self.video_layout.addWidget(self.video_widget, stretch=1)

        self.timeline_layout = QHBoxLayout()
        self.lbl_current_time = QLabel("00:00")
        self.lbl_total_time = QLabel("00:00")

        for lbl in [self.lbl_current_time, self.lbl_total_time]:
            lbl.setStyleSheet("color: #cccccc; font-size: 11px; font-weight: bold;")

        self.slider_progress = SafeJumpSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_progress.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3e3e42; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #007acc; border-radius: 3px; }
            QSlider::handle:horizontal { background: white; width: 12px; margin: -3px 0; border-radius: 6px; }
        """)

        self.timeline_layout.addWidget(self.lbl_current_time)
        self.timeline_layout.addWidget(self.slider_progress)
        self.timeline_layout.addWidget(self.lbl_total_time)
        self.video_layout.addLayout(self.timeline_layout)

        self.controls_layout = QHBoxLayout()
        self.controls_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_skip_back = QPushButton()
        self.btn_skip_back.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "back 10Sec.svg"))))
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "pause.svg"))))
        self.btn_skip_forward = QPushButton()
        self.btn_skip_forward.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "skip 10Sec.svg"))))

        for btn in [self.btn_skip_back, self.btn_play_pause, self.btn_skip_forward]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 5px 12px;
                    background-color: #3e3e42;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #505050; }
            """)
            self.controls_layout.addWidget(btn)

        self.video_layout.addLayout(self.controls_layout)
        self.stack.addWidget(self.video_container)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.5)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.mediaStatusChanged.connect(self._check_loop)
        self.media_player.playbackStateChanged.connect(self._update_play_button)
        self.media_player.positionChanged.connect(self._update_position)
        self.media_player.durationChanged.connect(self._update_duration)

        self.slider_progress.sliderMoved.connect(self._set_position)

        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        self.btn_skip_back.clicked.connect(lambda: self.skip(-10000))
        self.btn_skip_forward.clicked.connect(lambda: self.skip(10000))

    def _format_time(self, ms):
        """Converts milliseconds into MM:SS or HH:MM:SS format"""
        s = round(ms / 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    def _update_position(self, position):
        if not self.slider_progress.isSliderDown():
            self.slider_progress.setValue(position)
        self.lbl_current_time.setText(self._format_time(position))

    def _update_duration(self, duration):
        self.slider_progress.setRange(0, duration)
        self.lbl_total_time.setText(self._format_time(duration))

    def _set_position(self, position):
        """Safely seeks by temporarily pausing the video to free up the decoder."""
        was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

        if was_playing:
            self.media_player.pause()

        self.media_player.setPosition(position)

        if was_playing:
            self.media_player.play()

    def _check_loop(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.media_player.setPosition(0)
            self.media_player.play()

    def toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _update_play_button(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "pause.svg"))))
        else:
            self.btn_play_pause.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "play.svg"))))

    def skip(self, ms):
        """Skip buttons now use the freeze-proof safe seek."""
        new_pos = self.media_player.position() + ms
        max_pos = self.media_player.duration()
        new_pos = max(0, min(new_pos, max_pos))
        self._set_position(new_pos)

    def set_image(self, file_path):
        self.clear_image("")

        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 100:
                self.clear_image("Error: File is empty or corrupted.")
                return
        except OSError:
            self.clear_image("Error: Unable to read file data.")
            return

        ext = os.path.splitext(file_path)[1].lower()
        video_exts = {'.mp4', '.webm', '.mkv', '.mov', '.avi'}

        if ext in video_exts:
            self.stack.setCurrentIndex(1)
            self.media_player.setSource(QUrl.fromLocalFile(file_path))
            self.media_player.play()
        else:
            self.stack.setCurrentIndex(0)
            self.image_label.set_image(file_path)

    def clear_image(self, text="Select a file from the Inbox to work on"):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.stack.setCurrentIndex(0)
        self.image_label.clear_image(text)

class MultiTagCompleter(QCompleter):
    def __init__(self, parent=None):
        super().__init__(parent)

    def pathFromIndex(self, index):
        path = super().pathFromIndex(index)
        text = self.widget().text()
        if ',' in text:
            prefix = text[:text.rfind(',') + 1]
            return prefix + " " + path
        return path

    def splitPath(self, path):
        if ',' in path:
            return [path.split(',')[-1].strip()]
        return [path]


class PersistentCloudWorker(QThread):
    log_msg = pyqtSignal(str)

    def __init__(self, db_dir):
        super().__init__()
        self.db_dir = db_dir
        self.queue_db = os.path.join(self.db_dir, "cloud_queue.db")
        self.is_running = True
        self.ensure_db()

    def ensure_db(self):
        try:
            conn = sqlite3.connect(self.queue_db)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS upload_queue (
                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                              hash TEXT,
                              tags TEXT)''')
            conn.commit()
            conn.close()
        except Exception as e:
            self.log_msg.emit(f"CLOUD QUEUE ERR: {e}")

    def run(self):

        url = "https://jhzshjwkeljwuovfyasa.supabase.co/rest/v1/unapproved_queue"
        key = "sb_publishable_U38Za9kpw-oLzHFRMC5wyA_VuI6OElh"

        settings = QSettings("MediaNest", "CloudConfig")
        user_token = settings.value("anon_user_token", "", type=str)
        if not user_token:
            user_token = str(uuid.uuid4())
            settings.setValue("anon_user_token", user_token)

        headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=minimal"}

        while self.is_running:
            try:
                conn = sqlite3.connect(self.queue_db)
                conn.execute("PRAGMA journal_mode=WAL;")
                cursor = conn.cursor()
                cursor.execute("SELECT id, hash, tags FROM upload_queue ORDER BY id ASC LIMIT 1")
                row = cursor.fetchone()

                if not row:
                    conn.close()
                    time.sleep(2.0)
                    continue

                row_id, hash_val, tags_str = row
                payload = {"hash": hash_val, "suggested_tags": tags_str, "submitted_by_token": user_token}

                response = requests.post(url, json=payload, headers=headers, timeout=5)
                if response.status_code in [200, 201, 204]:
                    cursor.execute("DELETE FROM upload_queue WHERE id = ?", (row_id,))
                    conn.commit()
                else:
                    self.log_msg.emit(f"CLOUD SYNC WARN: Retrying in a few moments (HTTP {response.status_code})")
                    time.sleep(5.0)

                conn.close()
                time.sleep(0.5)
            except Exception as e:
                time.sleep(5.0)

    def stop(self):
        self.is_running = False
        self.wait()


class CloudSyncThread(QThread):
    progress = pyqtSignal(int, int)
    log_msg = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)

    def __init__(self, hashes):
        super().__init__()
        self.hashes = hashes

    def run(self):
        self.log_msg.emit(f"CLOUD SYNC: Contacting Supabase to check {len(self.hashes)} files...")
        url = "https://jhzshjwkeljwuovfyasa.supabase.co/rest/v1/global_tags_archive"
        key = "sb_publishable_U38Za9kpw-oLzHFRMC5wyA_VuI6OElh"
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}

        results = {}
        batch_size = 50

        for i in range(0, len(self.hashes), batch_size):
            if self.isInterruptionRequested(): break

            batch = self.hashes[i:i+batch_size]
            hash_list_str = ",".join(batch)

            try:
                req_url = f"{url}?select=hash,tags&hash=in.({hash_list_str})"
                response = requests.get(req_url, headers=headers, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    for row in data:
                        h = row.get("hash")
                        tags = [t.strip().lower().replace(" ", "_") for t in row.get("tags", "").split(",") if t.strip()]
                        if h and tags:
                            results[h] = tags
                else:
                    self.log_msg.emit(f"CLOUD SYNC WARN: Server responded with code {response.status_code}")
            except Exception as e:
                self.log_msg.emit(f"CLOUD SYNC ERROR: Network failure -> {e}")

            self.progress.emit(min(i + batch_size, len(self.hashes)), len(self.hashes))

        self.finished_signal.emit(results)

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, urls, dest_dir):
        super().__init__()
        self.urls = urls
        self.dest_dir = dest_dir

    def run(self):
        try:
            os.makedirs(self.dest_dir, exist_ok=True)
            for url, filename in self.urls:
                if self.isInterruptionRequested(): return
                self.status.emit(f"Downloading {filename}...")
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                total = int(response.headers.get('content-length', 0))

                path = os.path.join(self.dest_dir, filename)
                downloaded = 0
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.isInterruptionRequested(): return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                self.progress.emit(int((downloaded / total) * 100))
            self.finished_signal.emit(True, "")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class ImportFolderThread(QThread):
    progress = pyqtSignal(int)
    log_msg = pyqtSignal(str)
    finished_signal = pyqtSignal(int, int)
    item_imported = pyqtSignal(str, str, str)
    def __init__(self, folder_path, db_path):
        super().__init__()
        self.folder_path = folder_path
        self.db_path = db_path
        self.valid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm')

    def run(self):
        try:
            self.log_msg.emit(f"IMPORT: Scanning directory for media -> {self.folder_path}")
            files_to_process = []
            for root, _, files in os.walk(self.folder_path):
                for f in files:
                    if f.lower().endswith(self.valid_exts):
                        files_to_process.append(os.path.join(root, f))

            total = len(files_to_process)
            if total == 0:
                self.log_msg.emit("IMPORT: No valid media files found in selected directory.")
                self.finished_signal.emit(0, 0)
                return

            self.log_msg.emit(f"IMPORT: Found {total} media items. Hashing and indexing...")
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            imported = 0
            skipped = 0

            for i, file_path in enumerate(files_to_process):
                if self.isInterruptionRequested(): break
                hasher = hashlib.md5()
                try:
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                    file_hash = hasher.hexdigest()

                    cursor.execute("SELECT 1 FROM Images WHERE hash = ?", (file_hash,))
                    in_main = cursor.fetchone()
                    cursor.execute("SELECT 1 FROM tagless WHERE hash = ?", (file_hash,))
                    in_tagless = cursor.fetchone()

                    if in_main or in_tagless:
                        skipped += 1
                    else:
                        file_name = os.path.basename(file_path)

                        phash_value = None
                        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')):
                            try:
                                with Image.open(file_path) as img:
                                    phash_value = str(imagehash.phash(img, hash_size=16))
                            except Exception as e:
                                self.log_msg.emit(f"IMPORT WARN: Could not calculate phash for {file_name}")

                        cursor.execute("INSERT INTO tagless (hash, file_path, file_name, phash) VALUES (?, ?, ?, ?)",
                                       (file_hash, file_path, file_name, phash_value))
                        imported += 1
                        self.item_imported.emit(file_name, file_path, file_hash)
                except Exception as file_e:
                    self.log_msg.emit(f"IMPORT ERR: Failed to read {os.path.basename(file_path)}: {file_e}")

                if i % 50 == 0: conn.commit()
                self.progress.emit(int(((i + 1) / total) * 100))

            conn.commit()
            conn.close()
            self.finished_signal.emit(imported, skipped)
        except Exception as e:
            self.log_msg.emit(f"IMPORT CRASH: {e}")
            self.finished_signal.emit(-1, 0)

class ModelDownloadDialog(QDialog):
    def __init__(self, dest_dir, parent=None):
        super().__init__(parent)
        self.dest_dir = dest_dir
        self.setWindowTitle("Download AI Tagging Model")
        self.setMinimumWidth(420)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        lbl = QLabel("The AI models are missing.\nPlease select an engine to download:")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl)

        self.bg = QButtonGroup(self)
        self.rb_basic = QRadioButton("Basic - Fast (~379MB)")
        self.rb_balanced = QRadioButton("Balanced - Recommended (~440MB)")
        self.rb_advanced = QRadioButton("Advanced - Best Accuracy (~1.26GB)")

        self.bg.addButton(self.rb_basic, 0)
        self.bg.addButton(self.rb_balanced, 1)
        self.bg.addButton(self.rb_advanced, 2)
        self.rb_balanced.setChecked(True)

        layout.addWidget(self.rb_basic)
        layout.addWidget(self.rb_balanced)
        layout.addWidget(self.rb_advanced)

        self.lbl_status = QLabel("Ready.")
        self.lbl_status.setStyleSheet("color: #888;")
        layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_download = QPushButton("Download & Install")
        self.btn_download.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 6px;")
        self.btn_download.clicked.connect(self.start_download)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_download)
        layout.addLayout(btn_layout)

    def start_download(self):
        self.btn_download.setEnabled(False)
        self.rb_basic.setEnabled(False)
        self.rb_balanced.setEnabled(False)
        self.rb_advanced.setEnabled(False)
        self.progress.show()

        urls = {
            0: [("https://huggingface.co/SmilingWolf/wd-vit-tagger-v3/resolve/main/model.onnx", "model.onnx"),
                ("https://huggingface.co/SmilingWolf/wd-vit-tagger-v3/resolve/main/selected_tags.csv", "selected_tags.csv")],
            1: [("https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/model.onnx", "model.onnx"),
                ("https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/selected_tags.csv", "selected_tags.csv")],
            2: [("https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3/resolve/main/model.onnx", "model.onnx"),
                ("https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3/resolve/main/selected_tags.csv", "selected_tags.csv")]
        }

        selected_urls = urls[self.bg.checkedId()]
        self.thread = DownloadThread(selected_urls, self.dest_dir)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.status.connect(self.lbl_status.setText)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success, error_msg):
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Download Failed", error_msg)
            self.reject()


class TagManagerTab(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self, settings_dialog):
        super().__init__()
        self.settings_dialog = settings_dialog
        self.current_selected_file = None
        self.current_file_hash = None
        self.import_worker = None

        self.tag_completer_model = QStringListModel()
        self.known_gelbooru_chars = set()
        self.pending_cloud_matches = {}

        self.log_signal.connect(self.append_log_to_console)

        self.setup_ui()

        self.pending_thumbnails = {}
        self.thumbnail_map = {}
        self.pending_cloud_matches = {}
        self.pending_tag_changes = {}
        self.pending_renames = {}


        from Src.Logic.app import SingleThumbnailThread, VideoThumbnailer
        self.thumb_worker = SingleThumbnailThread(perf_mode="balanced")
        self.thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_worker.start()

        self.vid_thumb_worker = VideoThumbnailer()
        self.vid_thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)

        self.thumb_apply_timer = QTimer(self)
        self.thumb_apply_timer.timeout.connect(self.apply_pending_thumbnails)
        self.thumb_apply_timer.start(50)

        db_folder = self.settings_dialog.db_path_input.text().strip()
        if os.path.exists(db_folder):
            self.persistent_cloud_worker = PersistentCloudWorker(db_folder)
            self.persistent_cloud_worker.log_msg.connect(self.log)
            self.persistent_cloud_worker.start()

        self.log("SYSTEM BOOT: UI Initialized. Awaiting database connection.")

    def on_thumbnail_ready(self, path, qimage):
        self.pending_thumbnails[path] = qimage

    def apply_pending_thumbnails(self):
        if not self.pending_thumbnails:
            return

        keys_to_process = list(self.pending_thumbnails.keys())
        for path in keys_to_process:
            qimage = self.pending_thumbnails.pop(path, None)
            if qimage is None: continue

            item = self.thumbnail_map.get(path)
            if not item:
                norm_target = os.path.normpath(path)
                for k, v in self.thumbnail_map.items():
                    if os.path.normpath(k) == norm_target:
                        item = v
                        break

            if item:
                try:
                    if self.inbox_list_widget.row(item) != -1:
                        pixmap = QPixmap.fromImage(qimage)
                        item.setIcon(QIcon(pixmap))
                        if "⏳" in item.text():
                            clean_name = os.path.basename(path)
                            item.setText(clean_name)
                except RuntimeError:
                    pass

    def log(self, message):
        self.log_signal.emit(message)

    def append_log_to_console(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.console.appendPlainText(f"[{timestamp}] {message}")
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        col1_widget = QWidget()
        col1_layout = QVBoxLayout(col1_widget)
        col1_layout.setContentsMargins(0, 0, 5, 0)

        self.inbox_group = QGroupBox("Tag Management Index (Inbox Queue)")
        inbox_layout = QVBoxLayout()

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search existing tags (e.g., 'outdoor') or leave blank for Inbox...")
        self.search_bar.setStyleSheet("padding: 8px; border-radius: 4px; background-color: #252526; color: white; border: 1px solid #3e3e42;")
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self.search_library_by_tag)

        self.search_bar.textChanged.connect(self.search_timer.start)
        self.search_bar.returnPressed.connect(self.search_library_by_tag)
        self.search_completer = MultiTagCompleter()
        self.search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_completer.setModel(self.tag_completer_model)
        self.search_bar.setCompleter(self.search_completer)
        inbox_layout.addWidget(self.search_bar)

        self.btn_import_folder = QPushButton("Import External Folder")
        self.btn_import_folder.setAutoDefault(False)
        self.btn_import_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_folder.setStyleSheet("QPushButton { background-color: #007acc; font-weight: bold; border-radius: 4px; padding: 5px; } QPushButton:hover { background-color: #0098ff; }")
        self.btn_import_folder.clicked.connect(self.import_external_folder)
        inbox_layout.addWidget(self.btn_import_folder)

        self.btn_cloud_sync = QPushButton("Find Matches in Cloud")
        self.btn_cloud_sync.setAutoDefault(False)
        self.btn_cloud_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cloud_sync.setStyleSheet("QPushButton { background-color: #8957e5; color: white; font-weight: bold; border-radius: 4px; padding: 5px; } QPushButton:hover { background-color: #9a68f6; }")
        self.btn_cloud_sync.clicked.connect(self.sync_inbox_with_cloud)
        inbox_layout.addWidget(self.btn_cloud_sync)


        self.import_progress = QProgressBar()
        self.import_progress.setFixedHeight(8)
        self.import_progress.setTextVisible(False)
        self.import_progress.hide()
        inbox_layout.addWidget(self.import_progress)

        self.inbox_list_widget = QListWidget()
        self.inbox_list_widget.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;")
        self.inbox_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.inbox_list_widget.setIconSize(QSize(150, 150))
        self.inbox_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.inbox_list_widget.setSpacing(10)
        self.inbox_list_widget.setMovement(QListWidget.Movement.Static)
        self.inbox_list_widget.setWordWrap(True)
        self.inbox_list_widget.itemClicked.connect(self.on_inbox_item_selected)
        inbox_layout.addWidget(self.inbox_list_widget)

        self.inbox_group.setLayout(inbox_layout)
        col1_layout.addWidget(self.inbox_group)

        col2_widget = QWidget()
        col2_layout = QVBoxLayout(col2_widget)
        col2_layout.setContentsMargins(5, 0, 5, 0)

        rename_group = QGroupBox("File Rename")
        rename_layout = QHBoxLayout()
        self.rename_input = QLineEdit()
        self.rename_input.setPlaceholderText("File name (without extension)")
        self.rename_input.setStyleSheet("padding: 5px; border-radius: 4px; background-color: #252526; color: white; border: 1px solid #3e3e42;")

        self.lbl_rename_error = QLabel("⚠️ Name exists!")
        self.lbl_rename_error.setStyleSheet("color: #ff5252; font-weight: bold; font-size: 11px;")
        self.lbl_rename_error.setToolTip("A file with this name already exists in this folder.")
        self.lbl_rename_error.hide()

        from PyQt6.QtGui import QRegularExpressionValidator
        from PyQt6.QtCore import QRegularExpression
        regex = QRegularExpression(r'[^<>:"/\\|?*]+')
        self.rename_input.setValidator(QRegularExpressionValidator(regex, self.rename_input))
        self.rename_input.textChanged.connect(self.mark_current_file_renamed)

        rename_layout.addWidget(self.rename_input)
        rename_layout.addWidget(self.lbl_rename_error)
        rename_group.setLayout(rename_layout)
        col2_layout.addWidget(rename_group)

        active_tags_group = QGroupBox("Active Tags (Double-click to delete)")
        active_tags_layout = QVBoxLayout()

        self.active_tags_search = QLineEdit()
        self.active_tags_search.setPlaceholderText("Filter active tags...")
        self.active_tags_search.setStyleSheet("padding: 5px; border-radius: 4px; background-color: #252526; color: white; border: 1px solid #3e3e42;")
        self.active_tags_search.textChanged.connect(self.filter_active_tags)
        active_tags_layout.addWidget(self.active_tags_search)

        self.file_tag_list = QListWidget()
        self.file_tag_list.setStyleSheet("""
            QListWidget { background-color: #1e1e1e; border-radius: 4px; padding: 5px; color: #58a6ff; }
            QListWidget::item { padding: 5px; }
            QListWidget::item:hover { background-color: #3e3e42; border-radius: 3px; }
        """)

        add_tag_layout = QHBoxLayout()
        add_tag_layout.setSpacing(8)

        self.input_add_tag = QLineEdit()
        self.input_add_tag.setFixedHeight(34)
        self.input_add_tag.setPlaceholderText("Add tag manually...")
        self.input_add_tag.setStyleSheet("border-radius: 4px; padding-left: 8px;")

        self.tag_completer = MultiTagCompleter()
        self.tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_completer.setModel(self.tag_completer_model)
        self.tag_completer.setMaxVisibleItems(10)
        self.input_add_tag.setCompleter(self.tag_completer)

        self.btn_add_tag = QPushButton()
        self.btn_add_tag.setFixedHeight(34)
        self.btn_add_tag.setFixedWidth(40)
        self.btn_add_tag.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "add.svg"))))
        self.btn_add_tag.setIconSize(QSize(20, 20))
        self.btn_add_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_tag.setStyleSheet("QPushButton { background-color: #3e3e42; border-radius: 4px; border: none; padding-left: 10px; padding-right: 10px; } QPushButton:hover { background-color: #505050; }")
        self.btn_add_tag.clicked.connect(self.add_tag_to_current_list)
        self.input_add_tag.returnPressed.connect(self.add_tag_to_current_list)

        self.btn_auto_tag = QPushButton("AI Tag")
        self.btn_auto_tag.setFixedHeight(34)
        self.btn_auto_tag.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "ai.svg"))))
        self.btn_auto_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_tag.setStyleSheet("QPushButton { background-color: #512da8; color: white; font-weight: bold; border-radius: 4px; padding: 0 15px; border: none; } QPushButton:hover { background-color: #673ab7; }")
        self.btn_auto_tag.clicked.connect(self.run_auto_tagger)

        add_tag_layout.addWidget(self.input_add_tag)
        add_tag_layout.addWidget(self.btn_add_tag)
        add_tag_layout.addWidget(self.btn_auto_tag)

        self.btn_remove_file_tag = QPushButton("Delete Selected Active Tag")
        self.btn_remove_file_tag.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "remove.svg"))))
        self.btn_remove_file_tag.clicked.connect(self.delete_checked_tags)

        active_tags_layout.addWidget(self.file_tag_list)
        active_tags_layout.addLayout(add_tag_layout)
        active_tags_layout.addWidget(self.btn_remove_file_tag)
        active_tags_group.setLayout(active_tags_layout)

        col2_layout.addWidget(active_tags_group)

        col3_widget = QWidget()
        col3_layout = QVBoxLayout(col3_widget)
        col3_layout.setContentsMargins(5, 0, 0, 0)

        workspace_group = QGroupBox("Media Workspace")
        workspace_layout = QVBoxLayout()

        self.lbl_tag_preview = UniversalMediaViewer("Select a file from the Inbox to work on")
        workspace_layout.addWidget(self.lbl_tag_preview, stretch=7)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #0c0c0c; color: #4CAF50; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #3e3e42; border-radius: 4px;")
        workspace_layout.addWidget(self.console, stretch=3)

        self.workspace_btn_layout = QHBoxLayout()

        self.btn_approve_all_cloud = QPushButton("Batch Approve All")
        self.btn_approve_all_cloud.setMinimumHeight(40)
        self.btn_approve_all_cloud.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_approve_all_cloud.setStyleSheet("QPushButton { background-color: #238636; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #2ea043; }")
        self.btn_approve_all_cloud.clicked.connect(self.batch_approve_all_cloud)
        self.btn_approve_all_cloud.hide()

        self.btn_save_archive = QPushButton("Save All Pending Changes")
        self.btn_save_archive.setMinimumHeight(40)
        self.btn_save_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
        self.btn_save_archive.clicked.connect(self.graduate_file_to_archive)

        self.workspace_btn_layout.addWidget(self.btn_approve_all_cloud)
        self.workspace_btn_layout.addWidget(self.btn_save_archive)

        workspace_layout.addLayout(self.workspace_btn_layout)

        workspace_group.setLayout(workspace_layout)
        col3_layout.addWidget(workspace_group)

        self.splitter.addWidget(col1_widget)
        self.splitter.addWidget(col2_widget)
        self.splitter.addWidget(col3_widget)
        self.splitter.setSizes([719, 334, 644])

        main_layout.addWidget(self.splitter)

        self.cb_help_others = QCheckBox("Help others by anonymously sharing these tags to the community cloud")
        self.cb_help_others.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "handshake.svg"))))
        self.cb_help_others.setIconSize(QSize(20, 20))
        self.cb_help_others.setChecked(True)
        self.cb_help_others.setStyleSheet("QCheckBox { color: #888; font-style: italic; font-size: 13px; }")

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cb_help_others)
        main_layout.addLayout(bottom_layout)


    def get_db_paths(self):
        settings = QSettings("MediaNest", "AppConfig")
        db_folder = settings.value("db_folder_path", "", type=str)
        library_db = os.path.join(db_folder, "library.db")

        characters_db = os.path.join(db_folder, "characters.db")

        if not os.path.exists(characters_db):
            alt_db = os.path.join(db_folder, "character.db")
            if os.path.exists(alt_db):
                characters_db = alt_db
            else:
                if getattr(sys, 'frozen', False):
                    app_dir = os.path.dirname(sys.executable)
                else:
                    app_dir = os.path.abspath(".")

                root_db = os.path.join(app_dir, "characters.db")
                if os.path.exists(root_db):
                    characters_db = root_db

        return library_db, characters_db

    def import_external_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select External Folder to Import")
        if not folder_path: return
        library_db, _ = self.get_db_paths()
        if not os.path.exists(library_db): return

        self.btn_import_folder.setEnabled(False)
        self.import_progress.setValue(0)
        self.import_progress.show()

        self.import_worker = ImportFolderThread(folder_path, library_db)
        self.import_worker.progress.connect(self.import_progress.setValue)
        self.import_worker.log_msg.connect(self.log)
        self.import_worker.item_imported.connect(self.add_single_streamed_item)
        self.import_worker.finished_signal.connect(self.on_import_finished)
        self.import_worker.start()

    def add_single_streamed_item(self, file_name, file_path, file_hash):
        """Catches items from the background thread and injects them into the UI instantly."""
        empty_pixmap = QPixmap(150, 150)
        empty_pixmap.fill(Qt.GlobalColor.transparent)

        item = QListWidgetItem()
        item.setToolTip(file_name)
        item.setIcon(QIcon(empty_pixmap))

        item.setData(Qt.ItemDataRole.UserRole, {"path": file_path, "hash": file_hash})
        self.thumbnail_map[file_path] = item
        self.inbox_list_widget.addItem(item)

        if any(file_name.lower().endswith(e) for e in ('.mp4', '.mkv', '.avi', '.webm', '.mov')):
            self.vid_thumb_worker.add_to_queue([file_path])
        else:
            self.thumb_worker.add_to_queue([file_path])

        self.inbox_list_widget.scrollToBottom()

    def on_import_finished(self, imported, skipped):
        self.btn_import_folder.setEnabled(True)
        self.import_progress.hide()
        if imported != -1: self.refresh_tagless_inbox()

    def refresh_global_tags(self):
        library_db, characters_db = self.get_db_paths()
        all_tags = []
        char_tags = []

        def normalize_tag(t): return str(t).strip().lower().replace(" ", "_")

        if os.path.exists(library_db):
            try:
                conn = self.settings_dialog.shared_conn
                cursor = conn.cursor()
                cursor.execute("SELECT tag_name FROM Tags")
                all_tags = [normalize_tag(row[0]) for row in cursor.fetchall() if row[0]]
            except Exception: pass

        if os.path.exists(characters_db):
            try:
                conn = sqlite3.connect(characters_db)
                conn.execute("PRAGMA journal_mode=WAL;")
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [t[0] for t in cursor.fetchall()]

                if tables:
                    target_table = "characters" if "characters" in tables else tables[0]

                    cursor.execute(f"PRAGMA table_info({target_table})")
                    columns = [col[1] for col in cursor.fetchall()]

                    if columns:
                        col_name = "character_name" if "character_name" in columns else columns[0]
                        col_alias = "raw_string" if "raw_string" in columns else (columns[1] if len(columns) > 1 else None)

                        if col_alias:
                            cursor.execute(f"SELECT {col_name}, {col_alias} FROM {target_table}")
                            rows = cursor.fetchall()
                            for c_name, r_str in rows:
                                if c_name:
                                    clean_c_name = normalize_tag(c_name)
                                    char_tags.append(clean_c_name)
                                    self.known_gelbooru_chars.add(clean_c_name)
                                if r_str:
                                    alias_part = str(r_str)
                                    if '=' in alias_part: alias_part = alias_part.split('=', 1)[1]
                                    for alias in alias_part.split(','):
                                        clean_alias = normalize_tag(alias)
                                        if clean_alias and clean_alias not in self.known_gelbooru_chars:
                                            char_tags.append(clean_alias)
                                            self.known_gelbooru_chars.add(clean_alias)
                        else:
                            cursor.execute(f"SELECT {col_name} FROM {target_table}")
                            rows = cursor.fetchall()
                            for c_name in rows:
                                if c_name[0]:
                                    clean_c_name = normalize_tag(c_name[0])
                                    char_tags.append(clean_c_name)
                                    self.known_gelbooru_chars.add(clean_c_name)

                conn.close()
            except Exception as e:
                self.log(f"WARN: Could not read character database: {e}")

        combined_set = set(all_tags + char_tags)
        combined_list = sorted(list(combined_set))
        self.tag_completer_model.setStringList(combined_list)

    def refresh_tagless_inbox(self):
        self.inbox_list_widget.clear()
        self.thumbnail_map.clear()
        self.thumb_worker.clear_queue()
        self.vid_thumb_worker.clear_queue()

        library_db, _ = self.get_db_paths()
        if not os.path.exists(library_db): return

        try:
            conn = self.settings_dialog.shared_conn
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM tagless
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM tagless
                    GROUP BY hash
                )
            """)
            conn.commit()

            cursor.execute("SELECT file_name, file_path, hash FROM tagless ORDER BY file_name ASC")
            rows = cursor.fetchall()

            invalid_hashes = []
            valid_items_count = 0

            files_for_img_thumbs = []
            files_for_vid_thumbs = []

            for file_name, file_path, file_hash in rows:

                if not file_path or not os.path.exists(file_path):
                    invalid_hashes.append(file_hash)
                    continue

                valid_items_count += 1

                empty_pixmap = QPixmap(150, 150)
                empty_pixmap.fill(Qt.GlobalColor.transparent)

                item = QListWidgetItem()
                item.setToolTip(file_name)
                item.setIcon(QIcon(empty_pixmap))

                if file_hash in self.pending_tag_changes:
                    item.setBackground(QColor(45, 125, 70, 100))

                item.setData(Qt.ItemDataRole.UserRole, {"path": file_path, "hash": file_hash})
                self.thumbnail_map[file_path] = item
                self.inbox_list_widget.addItem(item)

                if any(file_name.lower().endswith(e) for e in ('.mp4', '.mkv', '.avi', '.webm', '.mov')):
                    files_for_vid_thumbs.append(file_path)
                else:
                    files_for_img_thumbs.append(file_path)

            if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
            if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

            if invalid_hashes:
                for h in invalid_hashes:
                    cursor.execute("DELETE FROM tagless WHERE hash = ?", (h,))
                conn.commit()
                self.log(f"[DB: library.db] Inbox Cleanup: Removed {len(invalid_hashes)} missing files from database.")

            self.log(f"[DB: library.db] Tagless Queue synchronized. ({valid_items_count} items)")

        except Exception as e:
            self.log(f"TAGLESS SYNC ERR: {e}")

    def search_library_by_tag(self):
        """Searches the main library for a tag. If empty, loads the Tagless Inbox."""
        search_text = self.search_bar.text().strip().lower()
        self.inbox_list_widget.clear()
        self.file_tag_list.clear()
        self.thumbnail_map.clear()
        self.thumb_worker.clear_queue()
        self.vid_thumb_worker.clear_queue()

        library_db, _ = self.get_db_paths()
        if not os.path.exists(library_db): return

        conn = self.settings_dialog.shared_conn
        cursor = conn.cursor()

        tags_to_search = [t.strip() for t in search_text.split(',') if t.strip()]

        if not tags_to_search:
            self.inbox_group.setTitle("Tag Management Index (Inbox Queue)")
            self.refresh_tagless_inbox()
            return

        self.inbox_group.setTitle(f"Tag Management Index (Results for: {search_text})")

        query = "SELECT hash, file_path, file_name FROM Images WHERE "
        conditions = []
        params = []
        for tag in tags_to_search:
            conditions.append("""
                hash IN (
                    SELECT it.hash
                    FROM ImageTags it
                    JOIN Tags t ON it.tag_id = t.tag_id
                    WHERE t.tag_name LIKE ?
                )
            """)
            params.append(f"%{tag}%")

        query += " AND ".join(conditions)
        cursor.execute(query, tuple(params))

        files_for_img_thumbs = []
        files_for_vid_thumbs = []

        for row in cursor.fetchall():
            file_hash, file_path, file_name = row

            empty_pixmap = QPixmap(150, 150)
            empty_pixmap.fill(Qt.GlobalColor.transparent)

            item = QListWidgetItem()
            item.setToolTip(file_name)
            item.setIcon(QIcon(empty_pixmap))

            if file_hash in self.pending_tag_changes:
                item.setBackground(QColor(45, 125, 70, 100))

            item.setData(Qt.ItemDataRole.UserRole, {"path": file_path, "hash": file_hash})
            self.thumbnail_map[file_path] = item
            self.inbox_list_widget.addItem(item)

            if any(file_name.lower().endswith(e) for e in ('.mp4', '.mkv', '.avi', '.webm', '.mov')):
                files_for_vid_thumbs.append(file_path)
            else:
                files_for_img_thumbs.append(file_path)

        if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
        if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

    def load_file_into_tagger(self, file_path, file_hash):
        if not os.path.exists(file_path): return

        self.current_selected_file = file_path
        self.current_file_hash = file_hash
        self.file_tag_list.clear()
        self.input_add_tag.clear()

        self.rename_input.blockSignals(True)
        if file_hash in self.pending_renames:
            current_name = self.pending_renames[file_hash]
            name_no_ext, _ = os.path.splitext(current_name)
            self.rename_input.setText(name_no_ext)
        else:
            base_name = os.path.basename(file_path)
            name_no_ext, _ = os.path.splitext(base_name)
            self.rename_input.setText(name_no_ext)
        self.rename_input.blockSignals(False)

        if file_hash in self.pending_tag_changes:
            for tag_name in self.pending_tag_changes[file_hash]:
                item = QListWidgetItem(tag_name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setForeground(QColor("#ff6b6b"))
                item.setData(Qt.ItemDataRole.UserRole, {"tag_id": None, "tag_name": tag_name, "is_saved": False})
                self.file_tag_list.addItem(item)

            self.btn_save_archive.setEnabled(True)
            self.btn_save_archive.setText("Save All Pending Changes")
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
            self.btn_approve_all_cloud.hide()

        else:
            library_db, _ = self.get_db_paths()
            if os.path.exists(library_db):
                conn = self.settings_dialog.shared_conn
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM tagless WHERE hash = ?", (file_hash,))
                is_in_tagless = cursor.fetchone() is not None
                cursor.execute("""
                    SELECT t.tag_id, t.tag_name
                    FROM Tags t
                    JOIN ImageTags it ON t.tag_id = it.tag_id
                    WHERE it.hash = ?
                """, (file_hash,))

                for row in cursor.fetchall():
                    tag_id, tag_name = row
                    item = QListWidgetItem(tag_name)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setForeground(QColor("#ff6b6b"))
                    item.setData(Qt.ItemDataRole.UserRole, {"tag_id": tag_id, "tag_name": tag_name, "is_saved": True})
                    self.file_tag_list.addItem(item)

            if file_hash in self.pending_cloud_matches:
                for tag in self.pending_cloud_matches[file_hash]:
                    item = QListWidgetItem(f"{tag}")
                    item.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "cloud.svg"))))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setForeground(QColor("#b388ff"))
                    self.file_tag_list.addItem(item)

            if not is_in_tagless:
                self.btn_save_archive.setEnabled(False)
                self.btn_save_archive.setText("Already Archived")
                self.btn_save_archive.setStyleSheet("QPushButton { background-color: #2d2d2d; color: #666666; font-weight: bold; font-size: 14px; border-radius: 4px; border: 1px solid #3e3e42; }")
                self.btn_approve_all_cloud.hide()

            elif file_hash in self.pending_cloud_matches:
                self.btn_save_archive.setEnabled(True)
                self.btn_save_archive.setText("Approve Selected")
                self.btn_save_archive.setStyleSheet("QPushButton { background-color: #8957e5; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #9a68f6; }")
                self.btn_approve_all_cloud.show()

            else:
                self.btn_save_archive.setEnabled(True)
                self.btn_save_archive.setText("Save All Pending Changes")
                self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
                self.btn_approve_all_cloud.hide()


        self.lbl_tag_preview.set_image(file_path)

    def on_inbox_item_selected(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data: self.load_file_into_tagger(data["path"], data["hash"])

    def mark_current_file_renamed(self, new_text):
        if not self.current_file_hash or not self.current_selected_file: return

        base_name = os.path.basename(self.current_selected_file)
        name_no_ext, ext = os.path.splitext(base_name)

        self.lbl_rename_error.hide()

        if new_text != name_no_ext and new_text.strip() != "":
            target_name = new_text.strip() + ext
            target_path = os.path.join(os.path.dirname(self.current_selected_file), target_name)

            if os.path.exists(target_path) and target_path != self.current_selected_file:
                self.lbl_rename_error.show()
                self.pending_renames.pop(self.current_file_hash, None)
            else:
                self.pending_renames[self.current_file_hash] = target_name
        else:
            self.pending_renames.pop(self.current_file_hash, None)

        self.wake_up_save_button()

    def mark_current_file_changed(self):
        if not self.current_file_hash: return

        current_tags = []
        for i in range(self.file_tag_list.count()):
            tag_text = self.file_tag_list.item(i).text().replace("☁️ ", "").replace("☁️", "").strip()
            if tag_text: current_tags.append(tag_text)

        self.pending_tag_changes[self.current_file_hash] = current_tags

        if self.current_selected_file in self.thumbnail_map:
            item = self.thumbnail_map[self.current_selected_file]
            item.setBackground(QColor(45, 125, 70, 100))

        self.wake_up_save_button()

    def add_tag_to_current_list(self):
        tag_value = self.input_add_tag.text().strip().lower().replace(" ", "_")
        if not tag_value: return

        existing_items = []
        for i in range(self.file_tag_list.count()):
            t = self.file_tag_list.item(i).text()
            t = t.replace("☁️ ", "").replace("☁️", "").strip()
            existing_items.append(t)

        if tag_value not in existing_items:
            item = QListWidgetItem(tag_value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.file_tag_list.addItem(item)
            self.mark_current_file_changed()

        self.input_add_tag.clear()

    def filter_active_tags(self, text):
        search_text = text.lower()
        for i in range(self.file_tag_list.count()):
            item = self.file_tag_list.item(i)
            tag_name = item.text().lower()
            item.setHidden(search_text not in tag_name)

    def delete_checked_tags(self):
        """Finds all checked tags and deletes them from the UI and Database."""
        if not self.current_file_hash: return

        items_to_delete = []
        for i in range(self.file_tag_list.count()):
            item = self.file_tag_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items_to_delete.append(item)

        if not items_to_delete:
            return

        reply = QMessageBox.question(self, "Delete Tags",
                                     f"Are you sure you want to remove {len(items_to_delete)} selected tags from this image?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            for item in items_to_delete:
                self.file_tag_list.takeItem(self.file_tag_list.row(item))

            self.mark_current_file_changed()
            self.log(f"Removed {len(items_to_delete)} tags (Pending Save).")

    def run_auto_tagger(self):
        if not self.current_selected_file: return

        db_folder = self.settings_dialog.db_path_input.text().strip()
        models_dir = os.path.join(db_folder, "models")
        model_path = os.path.join(models_dir, "model.onnx")
        csv_path = os.path.join(models_dir, "selected_tags.csv")

        if not os.path.exists(model_path) or not os.path.exists(csv_path):
            dialog = ModelDownloadDialog(models_dir, self)
            if dialog.exec() == QDialog.DialogCode.Accepted: VisualSorter._instance = None
            else: return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            sorter = VisualSorter.get_instance(model_path, csv_path)
            result = sorter.process_image(self.current_selected_file)

            if result:
                new_tags = []
                if result.get("best_char"): new_tags.append(result["best_char"].lower().replace(" ", "_"))

                for tag_name, score in result.get("top_tags", []):
                    if score >= 0.12:
                        new_tags.append(tag_name.lower().replace(" ", "_"))

                new_tags = new_tags[:31]

                existing_items = []
                for i in range(self.file_tag_list.count()):
                    t = self.file_tag_list.item(i).text()
                    t = t.replace("☁️ ", "").replace("☁️", "").strip()
                    existing_items.append(t)

                added_new_tags = False
                for t in new_tags:
                    if t not in existing_items:
                        item = QListWidgetItem(t)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Unchecked)
                        self.file_tag_list.addItem(item)
                        added_new_tags = True

                if added_new_tags:
                    self.wake_up_save_button()
        except Exception as e:
            self.log(f"AI CRITICAL: Engine failure -> {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def sync_inbox_with_cloud(self):
        library_db, _ = self.get_db_paths()
        if not os.path.exists(library_db): return

        hashes_to_check = []
        try:
            conn = self.settings_dialog.shared_conn
            cursor = conn.cursor()
            cursor.execute("SELECT hash FROM tagless")
            hashes_to_check = [row[0] for row in cursor.fetchall()]
        except Exception: pass

        if not hashes_to_check: return

        self.btn_cloud_sync.setEnabled(False)
        self.import_progress.setMaximum(len(hashes_to_check))
        self.import_progress.setValue(0)
        self.import_progress.show()

        self.cloud_sync_worker = CloudSyncThread(hashes_to_check)
        self.cloud_sync_worker.progress.connect(self.import_progress.setValue)
        self.cloud_sync_worker.log_msg.connect(self.log)
        self.cloud_sync_worker.finished_signal.connect(self.on_cloud_sync_finished)
        self.cloud_sync_worker.start()

    def on_cloud_sync_finished(self, cloud_results):
        self.btn_cloud_sync.setEnabled(True)
        self.import_progress.hide()

        if not cloud_results:
            self.log("CLOUD SYNC COMPLETE: No matching tags found.")
            return

        self.log(f"CLOUD SYNC COMPLETE: Found community tags for {len(cloud_results)} files! Ready for review.")
        self.pending_cloud_matches = cloud_results

        self.refresh_tagless_inbox()

    def batch_approve_all_cloud(self):
        if not self.pending_cloud_matches: return

        reply = QMessageBox.question(self, "Batch Approve", f"Are you sure you want to blindly accept the cloud tags for {len(self.pending_cloud_matches)} files and graduate them into your library?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No: return

        library_db, _ = self.get_db_paths()
        try:
            conn = self.settings_dialog.shared_conn
            cursor = conn.cursor()
            successful = 0

            for file_hash, tags in self.pending_cloud_matches.items():
                cursor.execute("SELECT file_path, file_name, phash FROM tagless WHERE hash = ?", (file_hash,))
                row = cursor.fetchone()
                if row:
                    file_path, file_name, phash_value = row
                    cursor.execute("INSERT OR IGNORE INTO Images (hash, file_path, file_name, phash) VALUES (?, ?, ?, ?)", (file_hash, file_path, file_name, phash_value))
                    for tag in tags:
                        cursor.execute("INSERT OR IGNORE INTO Tags (tag_name) VALUES (?)", (tag,))
                        cursor.execute("SELECT tag_id FROM Tags WHERE tag_name = ?", (tag,))
                        tag_id = cursor.fetchone()[0]
                        cursor.execute("INSERT OR IGNORE INTO ImageTags (hash, tag_id) VALUES (?, ?)", (file_hash, tag_id))
                    cursor.execute("DELETE FROM tagless WHERE hash = ?", (file_hash,))
                    successful += 1

            conn.commit()

            self.log(f"BATCH APPROVAL: {successful} files archived.")
            self.pending_cloud_matches.clear()
            self.btn_approve_all_cloud.hide()

            self.btn_save_archive.setText("Archive and Save File")
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")

            if self.current_file_hash:
                self.lbl_tag_preview.clear_image("Select a file from the Inbox to work on")
                self.file_tag_list.clear()
                self.current_selected_file = None
                self.current_file_hash = None

            self.refresh_tagless_inbox()
            self.refresh_global_tags()
        except Exception as e:
            self.log(f"DB CRITICAL ERROR: {e}")




    def wake_up_save_button(self):
        """Wakes up the save button if a user adds new tags to an already archived file."""
        if not self.btn_save_archive.isEnabled():
            self.btn_save_archive.setEnabled(True)
            self.btn_save_archive.setText("Save Updates to Archive")
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")

    def graduate_file_to_archive(self):
        if self.current_file_hash:
            self.mark_current_file_changed()

        all_hashes = set(self.pending_tag_changes.keys()) | set(self.pending_renames.keys())
        if not all_hashes:
            QMessageBox.information(self, "No Changes", "There are no pending tag or name changes to save.")
            return

        library_db, _ = self.get_db_paths()
        if not os.path.exists(library_db): return

        reply = QMessageBox.question(self, "Save All Changes", f"You are about to permanently save changes for {len(all_hashes)} files. Proceed?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No: return

        self.log(f"Batch archiving/renaming {len(all_hashes)} files...")

        try:
            conn = self.settings_dialog.shared_conn
            cursor = conn.cursor()

            upload_queue = []

            for file_hash in list(all_hashes):
                file_path = None
                file_name = None
                tags = self.pending_tag_changes.get(file_hash)

                if file_hash == self.current_file_hash:
                    file_path = self.current_selected_file
                    file_name = os.path.basename(file_path) if file_path else None

                if not file_path:
                    for path, item in self.thumbnail_map.items():
                        data = item.data(Qt.ItemDataRole.UserRole)
                        if data and data.get("hash") == file_hash:
                            file_path = path
                            file_name = os.path.basename(path)
                            break

                if not file_path:
                    cursor.execute("SELECT file_path, file_name FROM tagless WHERE hash = ?", (file_hash,))
                    row = cursor.fetchone()
                    if row:
                        file_path, file_name = row
                    else:
                        cursor.execute("SELECT file_path, file_name FROM Images WHERE hash = ?", (file_hash,))
                        row = cursor.fetchone()
                        if row:
                            file_path, file_name = row
                        else:
                            continue

                if file_hash in self.pending_renames:
                    new_name = self.pending_renames[file_hash]
                    new_path = os.path.join(os.path.dirname(file_path), new_name)
                    if new_path != file_path:
                        try:
                            os.rename(file_path, new_path)
                            cursor.execute("UPDATE tagless SET file_path = ?, file_name = ? WHERE hash = ?", (new_path, new_name, file_hash))
                            cursor.execute("UPDATE Images SET file_path = ?, file_name = ? WHERE hash = ?", (new_path, new_name, file_hash))

                            if file_hash == self.current_file_hash:
                                self.current_selected_file = new_path

                            if file_path in self.thumbnail_map:
                                item = self.thumbnail_map.pop(file_path)
                                data = item.data(Qt.ItemDataRole.UserRole)
                                if data:
                                    data["path"] = new_path
                                    item.setData(Qt.ItemDataRole.UserRole, data)
                                self.thumbnail_map[new_path] = item

                            file_path = new_path
                            file_name = new_name
                        except OSError as e:
                            self.log(f"Failed to rename {file_name} to {new_name}: {e}")

                if tags is None:
                    continue

                cursor.execute("SELECT phash FROM tagless WHERE hash = ?", (file_hash,))
                row = cursor.fetchone()
                phash_value = row[0] if row else None

                cursor.execute("INSERT OR IGNORE INTO Images (hash, file_path, file_name, phash) VALUES (?, ?, ?, ?)", (file_hash, file_path, file_name, phash_value))

                cursor.execute("DELETE FROM ImageTags WHERE hash = ?", (file_hash,))

                for tag in tags:
                    if not tag: continue
                    cursor.execute("INSERT OR IGNORE INTO Tags (tag_name) VALUES (?)", (tag,))
                    cursor.execute("SELECT tag_id FROM Tags WHERE tag_name = ?", (tag,))
                    tag_id = cursor.fetchone()[0]
                    cursor.execute("INSERT OR IGNORE INTO ImageTags (hash, tag_id) VALUES (?, ?)", (file_hash, tag_id))

                cursor.execute("DELETE FROM tagless WHERE hash = ?", (file_hash,))

                if tags:
                    upload_queue.append((file_hash, tags))

                if file_hash in self.pending_cloud_matches:
                    del self.pending_cloud_matches[file_hash]

            conn.commit()

            if self.cb_help_others.isChecked() and upload_queue:
                db_folder = self.settings_dialog.db_path_input.text().strip()
                if os.path.exists(db_folder):
                    queue_db = os.path.join(db_folder, "cloud_queue.db")
                    try:
                        q_conn = sqlite3.connect(queue_db)
                        q_conn.execute("PRAGMA journal_mode=WAL;")
                        q_cursor = q_conn.cursor()
                        for file_hash, tags in upload_queue:
                            q_cursor.execute("INSERT INTO upload_queue (hash, tags) VALUES (?, ?)", (file_hash, ", ".join(tags)))
                        q_conn.commit()
                        q_conn.close()
                    except Exception as e:
                        self.log(f"CLOUD QUEUE INSERT ERR: {e}")

            self.pending_tag_changes.clear()
            self.pending_renames.clear()
            self.lbl_tag_preview.clear_image("Select a file from the Inbox to work on")
            self.file_tag_list.clear()
            self.current_selected_file = None
            self.current_file_hash = None

            self.btn_save_archive.setText("Save All Pending Changes")
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
            self.btn_approve_all_cloud.hide()

            self.refresh_global_tags()

            search_text = self.search_bar.text().strip()
            if search_text:
                self.search_library_by_tag()
            else:
                self.refresh_tagless_inbox()
            self.log("Batch Archiving completed successfully.")

        except Exception as e:
            self.log(f"DB CRITICAL ROLLBACK: Graduation failed -> {e}")