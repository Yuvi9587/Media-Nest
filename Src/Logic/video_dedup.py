import os
import sys
import json
import sqlite3
import subprocess
import requests
import zipfile
import re
from collections import defaultdict
from send2trash import send2trash

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QLabel, QScrollArea, QFrame, QSplitter, 
                             QMessageBox, QSlider, QProgressBar, QCheckBox)
from PyQt6.QtCore import Qt, QProcess, QThread, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from Src.Logic.paths import resource_path


class ClickableFrame(QFrame):
    """A custom widget that acts like a button so we can click the whole video card."""
    clicked = pyqtSignal(str, object)
    
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit(self.path, self)
        super().mousePressEvent(event)


class ThumbnailWorker(QThread):
    """Runs in the background to extract images without freezing the UI."""
    result_ready = pyqtSignal(str, bytes)

    def __init__(self, ffmpeg_path):
        super().__init__()
        self.queue = []
        self.is_running = True
        self.ffmpeg_path = ffmpeg_path

    def add_task(self, path, duration_sec):
        self.queue.append((path, duration_sec))
        if not self.isRunning():
            self.start()

    def run(self):
        while self.queue and self.is_running:
            path, dur = self.queue.pop(0)
            mid_time = max(0, dur / 2.0)
            try:
                cmd = [
                    self.ffmpeg_path, "-y", "-ss", str(mid_time),
                    "-i", path, "-vframes", "1",
                    "-f", "image2pipe", "-vcodec", "mjpeg", "-"
                ]
                with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=0x08000000) as process:
                    try:
                        out, _ = process.communicate(timeout=5)
                        if out:
                            self.result_ready.emit(path, out)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            except Exception:
                pass


class EngineDownloadThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log_msg = pyqtSignal(str) 
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, extract_dir):
        super().__init__()
        self.extract_dir = extract_dir
        self.vdf_url = "https://github.com/0x90d/videoduplicatefinder/releases/download/3.0.x/CLI-win-x64.zip"
        self.ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

    def _download_file(self, url, dest_path, status_text):
        self.status.emit(status_text)
        self.log_msg.emit(f"\n> [NETWORK] {status_text}")
        self.log_msg.emit(f"  ├─ Source: {url}")
        self.log_msg.emit(f"  └─ Target: {dest_path}")
        
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if self.isInterruptionRequested(): return False
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress.emit(int((downloaded / total) * 100))
        return True

    def run(self):
        import shutil
        try:
            self.log_msg.emit(f"> [SYSTEM] Initializing Engine Directory...")
            self.log_msg.emit(f"  └─ Path: {self.extract_dir}")
            os.makedirs(self.extract_dir, exist_ok=True)
            
            vdf_zip = os.path.join(self.extract_dir, "vdf.zip")
            if not self._download_file(self.vdf_url, vdf_zip, "Downloading VDF Engine..."): return
            
            self.status.emit("Extracting VDF Engine...")
            self.log_msg.emit(f"> [SYSTEM] Unzipping VDF Engine into workspace...")
            with zipfile.ZipFile(vdf_zip, 'r') as zip_ref:
                zip_ref.extractall(self.extract_dir)
            os.remove(vdf_zip)

            ffmpeg_zip = os.path.join(self.extract_dir, "ffmpeg.zip")
            if not self._download_file(self.ffmpeg_url, ffmpeg_zip, "Downloading FFmpeg... (Large File)"): return

            self.status.emit("Extracting FFmpeg...")
            self.log_msg.emit(f"> [SYSTEM] Parsing FFmpeg Archive (Extracting exact binaries only)...")
            with zipfile.ZipFile(ffmpeg_zip, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.endswith("ffmpeg.exe") or member.endswith("ffprobe.exe"):
                        filename = os.path.basename(member)
                        target_path = os.path.join(self.extract_dir, filename)
                        self.log_msg.emit(f"  ├─ Extracted: {filename} -> {target_path}")
                        
                        source = zip_ref.open(member)
                        target = open(target_path, "wb")
                        with source, target:
                            shutil.copyfileobj(source, target)
            os.remove(ffmpeg_zip)

            self.status.emit("Cleaning up...")
            self.log_msg.emit("> [SYSTEM] Installation routine completed successfully.")
            self.finished_signal.emit(True, "")
        except Exception as e:
            self.log_msg.emit(f"\n> [CRITICAL ERROR] Download failed: {str(e)}")
            self.finished_signal.emit(False, str(e))



class VideoDedupTab(QWidget):
    def __init__(self, settings_dialog):
        super().__init__()
        self.settings_dialog = settings_dialog
        
        self.vdf_process = QProcess()
        self.vdf_process.readyReadStandardOutput.connect(self.handle_stdout)
        self.vdf_process.readyReadStandardError.connect(self.handle_stderr)
        self.vdf_process.finished.connect(self.process_finished)
                
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(".") 
            
        self.engine_dir = os.path.join(base_dir, "Engine", "VideoDuplicateFinder")
        self.cli_path = os.path.join(self.engine_dir, "vdf-cli.exe")
        self.ffmpeg_path = os.path.join(self.engine_dir, "ffmpeg.exe") 
        self.output_json_path = os.path.join(base_dir, "vdf_results.json") 
        
        self.thumb_worker = ThumbnailWorker(self.ffmpeg_path)
        self.thumb_worker.result_ready.connect(self.apply_thumbnail)
        self.thumbnail_labels = {}
        self.active_video_widget = None
        
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        top_panel = QFrame()
        top_panel.setStyleSheet("background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42;")
        top_panel.setMaximumHeight(110) 
        
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(15, 10, 15, 10)
        
        settings_row = QHBoxLayout()
        self.lbl_sim = QLabel("Visual Match Requirement: 100%")
        self.lbl_sim.setStyleSheet("border: none; color: #cccccc; font-weight: bold;")
        
        self.slider_sim = QSlider(Qt.Orientation.Horizontal)
        self.slider_sim.setRange(80, 100)
        self.slider_sim.setValue(100)
        self.slider_sim.setFixedWidth(200)
        self.slider_sim.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_sim.setStyleSheet("border: none;")
        self.slider_sim.valueChanged.connect(lambda v: self.lbl_sim.setText(f"Visual Match Requirement: {v}%"))

        settings_row.addWidget(self.lbl_sim)
        settings_row.addWidget(self.slider_sim)
        settings_row.addStretch()
        top_layout.addLayout(settings_row)

        action_row = QHBoxLayout()
        
        self.btn_scan = QPushButton("Start Video Scan")
        self.btn_scan.setFixedSize(170, 32)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet("""
            QPushButton { background-color: #8957e5; color: white; font-weight: bold; border-radius: 4px; border: none; } 
            QPushButton:hover:!disabled { background-color: #9d6ceb; }
        """)
        self.btn_scan.clicked.connect(self.start_cli_scan)
        
        self.btn_download = QPushButton("Download VDF Engine")
        self.btn_download.setFixedSize(190, 32)
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; border: none; } 
            QPushButton:hover:!disabled { background-color: #0098ff; }
        """)
        self.btn_download.clicked.connect(self.download_engine)
        
        if os.path.exists(self.cli_path):
            self.btn_download.hide()
        
        self.lbl_status = QPushButton("Ready to find exact duplicate videos.")
        self.lbl_status.setStyleSheet("color: #0e639c; font-weight: bold; border: none; margin-left: 10px; text-align: left; background: transparent;")
        self.lbl_status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_status.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        action_row.addWidget(self.btn_scan)
        action_row.addWidget(self.btn_download)
        action_row.addWidget(self.lbl_status)
        action_row.addStretch()
        top_layout.addLayout(action_row)

        self.dl_progress = QProgressBar()
        self.dl_progress.setFixedHeight(8)
        self.dl_progress.setTextVisible(False)
        self.dl_progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #1e1e1e; border-radius: 4px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 4px; }
        """)
        self.dl_progress.hide()
        top_layout.addWidget(self.dl_progress)

        main_layout.addWidget(top_panel, 0) 

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px; }")
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content_widget)
        splitter.addWidget(self.scroll_area)

        right_panel = QSplitter(Qt.Orientation.Vertical)
        
        self.preview_frame = QFrame()
        self.preview_frame.setStyleSheet("background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px;")
        preview_layout = QVBoxLayout(self.preview_frame)
        
        self.lbl_preview_title = QPushButton("Video Player (Click a video to play)")
        self.lbl_preview_title.setStyleSheet("font-weight: bold; font-size: 1.1em; color: #ffffff; border: none; text-align: left; background: transparent;")
        self.lbl_preview_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_preview_title.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        preview_layout.addWidget(self.lbl_preview_title)
        
        self.video_widget = QVideoWidget()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.5) 
        
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        
        preview_layout.addWidget(self.video_widget, 1)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(5, 5, 5, 5)
        
        self.btn_skip_back = QPushButton()
        self.btn_skip_back.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "back 10Sec.svg"))))
        self.btn_skip_back.setStyleSheet("background-color: #3e3e42; border-radius: 4px; padding: 5px 12px;")
        self.btn_skip_back.clicked.connect(lambda: self.media_player.setPosition(self.media_player.position() - 10000))
        
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "play.svg"))))
        self.btn_play_pause.setStyleSheet("background-color: #3e3e42; border-radius: 4px; padding: 5px 12px;")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        
        self.btn_skip_forward = QPushButton()
        self.btn_skip_forward.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "skip 10Sec.svg"))))
        self.btn_skip_forward.setStyleSheet("background-color: #3e3e42; border-radius: 4px; padding: 5px 12px;")
        self.btn_skip_forward.clicked.connect(lambda: self.media_player.setPosition(self.media_player.position() + 10000))

        self.btn_external = QPushButton("Open Externally")
        self.btn_external.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_external.setStyleSheet("background-color: #3e3e42; border-radius: 4px; padding: 5px 12px; font-weight: bold; color: white;")
        self.btn_external.clicked.connect(self.open_external_player)

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.time_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3e3e42; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #8957e5; border-radius: 3px; }
            QSlider::handle:horizontal { background: white; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
            QSlider::handle:horizontal:hover { background: #d0d0d0; }
        """)
        
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #cccccc; font-size: 0.9em; font-weight: bold; font-family: Consolas;")

        controls_layout.addWidget(self.btn_skip_back)
        controls_layout.addWidget(self.btn_play_pause)
        controls_layout.addWidget(self.btn_skip_forward)
        controls_layout.addWidget(self.btn_external)
        controls_layout.addWidget(self.time_slider, stretch=1)
        controls_layout.addWidget(self.lbl_time)
        
        preview_layout.addLayout(controls_layout)

        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.media_player.errorOccurred.connect(self.on_media_error)
        self.time_slider.sliderMoved.connect(self.media_player.setPosition)

        right_panel.addWidget(self.preview_frame)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #0c0c0c; color: #cccccc; border: 1px solid #3e3e42; padding: 8px; border-radius: 4px; font-family: Consolas;")
        right_panel.addWidget(self.log_console)

        splitter.setSizes([600, 350])
        right_panel.setSizes([300, 300]) 
        splitter.addWidget(right_panel)
        main_layout.addWidget(splitter, 1)

        self.load_cached_results()

    def filter_ignored_vdf_groups(self, groups):
        if not groups: return groups, False
        
        db_folder = self.settings_dialog.db_path_input.text().strip()
        db_file = os.path.join(db_folder, "library.db")
        if not os.path.exists(db_file): return groups, False
        
        try:
            conn = self.settings_dialog.shared_conn
            cursor = conn.cursor()
            
            cursor.execute("CREATE TABLE IF NOT EXISTS IgnoredPairs (hash1 TEXT, hash2 TEXT, PRIMARY KEY (hash1, hash2))")
            cursor.execute("SELECT hash1, hash2 FROM IgnoredPairs")
            ignored_set = {tuple(sorted((row[0], row[1]))) for row in cursor.fetchall()}
            
            if not ignored_set:
                return groups, False

            all_paths = set()
            for g in groups:
                for item in g.get("Items", []):
                    all_paths.add(item["Path"])
            
            path_to_hash = {}
            cursor.execute("SELECT file_path, hash FROM Images")
            for p, h in cursor.fetchall():
                if p in all_paths: path_to_hash[p] = h
            
            valid_groups = []
            changes_made = False
            
            for group in groups:
                items = group.get("Items", [])
                valid_items = []
                
                for item in items:
                    h1 = path_to_hash.get(item["Path"])
                    can_add = True
                    if h1:
                        for v_item in valid_items:
                            h2 = path_to_hash.get(v_item["Path"])
                            if h2 and tuple(sorted((h1, h2))) in ignored_set:
                                can_add = False
                                break
                    
                    if can_add:
                        valid_items.append(item)
                    else:
                        changes_made = True
                        
                if len(valid_items) > 1:
                    if len(valid_items) != len(items):
                        group["Items"] = valid_items
                    valid_groups.append(group)
                else:
                    changes_made = True
                    
            return valid_groups, changes_made
            
        except Exception as e:
            self.log_console.append(f"> Filter Error: {e}")
            return groups, False

    def load_cached_results(self):
        if not os.path.exists(self.output_json_path):
            return

        try:
            with open(self.output_json_path, 'r', encoding='utf-8') as f:
                groups = json.load(f)

            if not groups:
                return

            valid_groups = []
            changes_made = False

            for group in groups:
                valid_items = []
                for item in group.get("Items", []):
                    if os.path.exists(item["Path"]):
                        valid_items.append(item)
                    else:
                        changes_made = True 

                if len(valid_items) > 1:
                    group["Items"] = valid_items
                    valid_groups.append(group)
                else:
                    changes_made = True

            valid_groups, filter_changed = self.filter_ignored_vdf_groups(valid_groups)

            if changes_made or filter_changed:
                with open(self.output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(valid_groups, f, indent=4)

            if valid_groups:
                self.log_console.append(f"> Fast Resume: Loaded {len(valid_groups)} duplicate groups from cache.")
                self.lbl_status.setText(f"Found {len(valid_groups)} exact duplicate groups (Cached).")
                self.render_video_groups(valid_groups)
                
        except Exception as e:
            self.log_console.append(f"> Cache Load Error: {e}")

    def download_engine(self):
        self.btn_download.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.dl_progress.setValue(0)
        self.dl_progress.show()
        
        self.log_console.clear()
        self.log_console.append("> Starting Engine Installation Process...")
        
        self.dl_worker = EngineDownloadThread(self.engine_dir)
        self.dl_worker.progress.connect(self.dl_progress.setValue)
        self.dl_worker.status.connect(self.lbl_status.setText)
        self.dl_worker.log_msg.connect(self.log_console.append)
        self.dl_worker.finished_signal.connect(self.on_download_finished)
        self.dl_worker.start()
        
    def on_download_finished(self, success, msg):
        self.dl_progress.hide()
        self.btn_download.setEnabled(True)
        self.btn_scan.setEnabled(True)
        
        if success:
            self.lbl_status.setText("Engine Installed Successfully!")
            self.btn_download.hide()
            QMessageBox.information(self, "Download Complete", "The Video Duplicate Finder engine has been successfully installed and is ready to use!")
        else:
            self.lbl_status.setText("Download Failed.")
            QMessageBox.critical(self, "Download Error", f"Failed to download the engine:\n{msg}")


    @pyqtSlot(str, object)
    def play_video(self, file_path, widget=None):
        play_icon = resource_path(os.path.join("assets", "uisvg", "play.svg")).replace('\\', '/')
        self.lbl_preview_title.setIcon(QIcon(play_icon))
        self.lbl_preview_title.setText(f" Playing: {os.path.basename(file_path)}")
        self._autoplay_pending = True
        
        if getattr(self, 'active_video_widget', None):
            try:
                self.active_video_widget.setStyleSheet("""
                    QFrame { background-color: #1e1e1e; border-radius: 6px; border: 1px solid #454545; }
                    QFrame:hover { border: 1px solid #8957e5; background-color: #2a2a2a; }
                """)
            except RuntimeError:
                self.active_video_widget = None
            
        self.active_video_widget = widget
        if self.active_video_widget:
            self.active_video_widget.setStyleSheet("""
                QFrame { background-color: rgba(137, 87, 229, 0.15); border-radius: 6px; border: 2px solid #8957e5; }
            """)
            
        self.media_player.setSource(QUrl.fromLocalFile(file_path))

    def toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "pause.svg"))))
        else:
            self.btn_play_pause.setIcon(QIcon(resource_path(os.path.join("assets", "Svg", "play.svg"))))

    def on_position_changed(self, position):
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(position)
        self.time_slider.blockSignals(False)
        self.update_time_label(position, self.media_player.duration())

    def on_duration_changed(self, duration):
        self.time_slider.setRange(0, duration)
        self.update_time_label(self.media_player.position(), duration)

    def update_time_label(self, position, duration):
        def format_ms(ms):
            seconds = (ms // 1000) % 60
            minutes = (ms // 60000) % 60
            hours = (ms // 3600000)
            if hours > 0:
                return f"{hours}:{minutes:02}:{seconds:02}"
            return f"{minutes:02}:{seconds:02}"
            
        self.lbl_time.setText(f"{format_ms(position)} / {format_ms(duration)}")

    def on_media_status_changed(self, status):
        # Auto-play as soon as the media is actually ready (avoids 0xC00D6D60)
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if getattr(self, '_autoplay_pending', False):
                self._autoplay_pending = False
                self.media_player.play()

    def on_media_error(self, error, error_string):
        self.log_console.append(f"> Media Player Error: {error_string} (Code: {error})")
        source = self.media_player.source().toLocalFile()
        if source:
            warn_icon = resource_path(os.path.join("assets", "uisvg", "warning.svg")).replace('\\', '/')
            self.lbl_preview_title.setIcon(QIcon(warn_icon))
            self.lbl_preview_title.setText(" Playback Error - Opening in System Player")
            QMessageBox.warning(self, "Unsupported Video Codec", f"Windows cannot play this video natively.\n\nError: {error_string}\n\nOpening it in your default system player instead (e.g. VLC or Windows Media Player).")
            try: os.startfile(source)
            except Exception as e: self.log_console.append(f"> Failed to open externally: {e}")

    def open_external_player(self):
        source = self.media_player.source().toLocalFile()
        if source:
            try: os.startfile(source)
            except Exception as e: self.log_console.append(f"> Failed to open externally: {e}")


    def start_cli_scan(self):
        if not os.path.exists(self.cli_path) or not os.path.exists(self.ffmpeg_path):
            QMessageBox.critical(self, "Engines Missing", "Required engines are missing.\n\nPlease click the 'Download VDF Engine' button to install them before scanning.")
            return

        db_folder = self.settings_dialog.db_path_input.text().strip()
        db_file = os.path.join(db_folder, "library.db")
        if not os.path.exists(db_file):
            QMessageBox.critical(self, "Error", "Could not find library.db.")
            return

        conn = self.settings_dialog.shared_conn
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT file_path FROM Images")
            all_files = [row[0] for row in cursor.fetchall() if row[0]]
            try:
                cursor.execute("SELECT file_path FROM tagless")
                all_files.extend([row[0] for row in cursor.fetchall() if row[0]])
            except sqlite3.OperationalError:
                pass
        except sqlite3.OperationalError:
            cursor.execute("SELECT file_name FROM characters")
            all_files = [row[0] for row in cursor.fetchall() if row[0]]

        video_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.wmv', '.m4v'}
        video_files = [f for f in all_files if os.path.splitext(f)[1].lower() in video_exts]

        if not video_files:
            self.lbl_status.setText("No videos found in database!")
            return

        unique_folders = set()
        for path in video_files:
            if os.path.exists(path):
                unique_folders.add(os.path.dirname(path))

        if len(unique_folders) > 75:
            drive_groups = defaultdict(list)
            for folder in unique_folders:
                drive = os.path.splitdrive(folder)[0]
                drive_groups[drive].append(folder)
                
            include_folders = []
            for drive, dir_paths in drive_groups.items():
                include_folders.append(os.path.commonpath(dir_paths))
        else:
            include_folders = list(unique_folders)

        if os.path.exists(self.output_json_path):
            try: os.remove(self.output_json_path)
            except: pass

        engine_folder = os.path.dirname(self.cli_path)
        
        try:
            subprocess.run(["taskkill", "/F", "/IM", "vdf-cli.exe"], capture_output=True, creationflags=0x08000000)
            subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], capture_output=True, creationflags=0x08000000)
        except Exception:
            pass 

        cache_db1 = os.path.join(engine_folder, "ScannedFiles.db")
        cache_db2 = os.path.join(engine_folder, "ScannedFiles_new.db")
        for cache_file in [cache_db1, cache_db2]:
            if os.path.exists(cache_file):
                try: 
                    os.remove(cache_file)
                except Exception as e: 
                    self.log_console.append(f"> WARNING: Could not delete cache file! It may be locked. ({e})")

        args = [
            "scan-and-compare", "--output", self.output_json_path,
            "--format", "json", "--use-phash", "--percent", str(self.slider_sim.value())
        ]
        for folder in include_folders:
            args.extend(["--include", folder])

        self.btn_scan.setEnabled(False)
        load_icon = resource_path(os.path.join("assets", "uisvg", "loading.svg")).replace('\\', '/')
        self.lbl_status.setIcon(QIcon(load_icon))
        self.lbl_status.setText(" Scanning... Please wait.")
        self.log_console.clear()
        
        self.dl_progress.setValue(0)
        self.dl_progress.show()
        
        self.log_console.append("=========================================")
        self.log_console.append("VIDEO DEDUPLICATION SCAN INITIATED")
        self.log_console.append("=========================================")
        self.log_console.append(f"> Target Database: {db_file}")
        self.log_console.append(f"> Result Output File: {self.output_json_path}")
        self.log_console.append(f"> Total videos queued for analysis: {len(video_files)}")
        self.log_console.append(">")
        self.log_console.append("> Target Directories to Scan:")
        for folder in include_folders:
            self.log_console.append(f"  ├─ {folder}")
        self.log_console.append(">")
        self.log_console.append("> Launching CLI Engine... Waiting for stdout...")
        self.log_console.append("-----------------------------------------")
        
        self.vdf_process.setWorkingDirectory(engine_folder)
        self.vdf_process.start(self.cli_path, args)

    def handle_stdout(self):
        out_data = self.vdf_process.readAllStandardOutput().data().decode(errors='replace')
        lines = out_data.replace('\r', '\n').split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if "%" in line:
                match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if match:
                    percent = float(match.group(1))
                    self.dl_progress.setValue(int(percent))
                    load_icon = resource_path(os.path.join("assets", "uisvg", "loading.svg")).replace('\\', '/')
                    self.lbl_status.setIcon(QIcon(load_icon))
                    self.lbl_status.setText(f" Scanning... {percent:.1f}%")
                
                if "ETA" in line or "]" in line:
                    continue
                    
            self.log_console.append(line)
            self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def handle_stderr(self):
        err_data = self.vdf_process.readAllStandardError().data().decode(errors='replace')
        lines = err_data.replace('\r', '\n').split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if "%" in line:
                match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if match:
                    percent = float(match.group(1))
                    self.dl_progress.setValue(int(percent))
                    load_icon = resource_path(os.path.join("assets", "uisvg", "loading.svg")).replace('\\', '/')
                    self.lbl_status.setIcon(QIcon(load_icon))
                    self.lbl_status.setText(f" Scanning... {percent:.1f}%")
                
                if "ETA" in line or "]" in line:
                    continue
            
            crash_keywords = ["Unhandled exception", "System.IO.IOException", "ScannedFiles_new.db", "at System.", "at VDF.", "at Microsoft."]
            if any(keyword in line for keyword in crash_keywords): continue
                
            self.log_console.append(line)
            self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def process_finished(self, exit_code, exit_status):
        self.btn_scan.setEnabled(True)
        self.dl_progress.hide()
        
        if os.path.exists(self.output_json_path):
            self.lbl_status.setText("Scan Complete! Processing results...")
            self.log_console.append("\n> Scan Complete! Parsing JSON results...")
            self.parse_vdf_results()
        else:
            self.lbl_status.setText("Scan Failed.")
            self.log_console.append(f"\n> [CRITICAL] Engine failed to write JSON. (Exit code {exit_code})")

    def parse_vdf_results(self):
        if not os.path.exists(self.output_json_path):
            return

        try:
            with open(self.output_json_path, 'r', encoding='utf-8') as f:
                groups = json.load(f)
                
            groups, filter_changed = self.filter_ignored_vdf_groups(groups)
            
            if filter_changed:
                with open(self.output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(groups, f, indent=4)
                
            if not groups:
                self.lbl_status.setText("Library is clean! No exact copies found.")
                self.render_video_groups([])
                return

            self.log_console.append(f"> Found {len(groups)} duplicate groups. Rendering UI...")
            self.lbl_status.setText(f"Found {len(groups)} exact duplicate groups.")
            self.render_video_groups(groups)
            
        except Exception as e:
            self.log_console.append(f"> JSON Parsing Error: {e}")

    @pyqtSlot(str, bytes)
    def apply_thumbnail(self, path, image_data):
        if path in self.thumbnail_labels:
            img = QImage()
            img.loadFromData(image_data)
            pixmap = QPixmap.fromImage(img).scaled(220, 124, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail_labels[path].setPixmap(pixmap)

    def render_video_groups(self, groups):
        self.thumb_worker.queue.clear()
        self.thumbnail_labels.clear()

        for i in reversed(range(self.content_layout.count())):
            w = self.content_layout.itemAt(i).widget()
            if w: w.setParent(None)

        for i, group in enumerate(groups):
            items = group.get("Items", [])
            if not items: continue

            group_card = QFrame()
            group_card.setStyleSheet("background-color: #2d2d30; border-radius: 8px; border: 1px solid #3e3e42; margin-bottom: 15px;")
            card_layout = QVBoxLayout(group_card)
            
            header_layout = QHBoxLayout()
            header = QLabel(f"Exact Duplicate Group #{i+1} ({len(items)} videos)")
            header.setStyleSheet("font-weight: bold; color: #ffffff; border: none; font-size: 1.1em; padding-bottom: 5px;")
            
            btn_ignore = QPushButton("Mark as 'Not Duplicates'")
            btn_ignore.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_ignore.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #3fb950; color: #3fb950; padding: 4px 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: rgba(63, 185, 80, 0.1); }")
            
            header_layout.addWidget(header)
            header_layout.addWidget(btn_ignore)
            header_layout.addStretch()
            card_layout.addLayout(header_layout)

            videos_container = QWidget()
            videos_container.setStyleSheet("background: transparent; border: none;") 
            videos_layout = QHBoxLayout(videos_container)
            videos_layout.setContentsMargins(0,0,0,0)
            videos_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

            has_checkboxes = len(items) >= 3
            checkbox_refs = []

            for vid in items:
                v_path = vid["Path"]
                v_name = os.path.basename(v_path)
                
                vid_widget = ClickableFrame(v_path)
                vid_widget.setFixedWidth(240)
                vid_widget.setStyleSheet("""
                    QFrame { background-color: #1e1e1e; border-radius: 6px; border: 1px solid #454545; }
                    QFrame:hover { border: 1px solid #8957e5; background-color: #2a2a2a; }
                """)
                vid_widget.clicked.connect(self.play_video)
                
                v_layout = QVBoxLayout(vid_widget)
                v_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                load_icon = resource_path(os.path.join("assets", "uisvg", "loading.svg")).replace('\\', '/')
                lbl_thumb = QToolButton()
                lbl_thumb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                lbl_thumb.setIcon(QIcon(load_icon))
                lbl_thumb.setIconSize(QSize(20, 20))
                lbl_thumb.setText("Loading Thumbnail...")
                lbl_thumb.setFixedSize(220, 124) 
                lbl_thumb.setStyleSheet("background-color: #000000; border-radius: 4px; color: #888888; border: none;")
                lbl_thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                lbl_thumb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.thumbnail_labels[v_path] = lbl_thumb 
                
                dur_str = vid.get('Duration', '00:00:00')
                try:
                    parts = dur_str.split('.')[0].split(':')
                    dur_sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                except:
                    dur_sec = 0
                
                self.thumb_worker.add_task(v_path, dur_sec)

                v_layout.addWidget(lbl_thumb)
                
                if has_checkboxes:
                    cb = QCheckBox("Select Exception")
                    cb.setCursor(Qt.CursorShape.PointingHandCursor)
                    cb.setProperty("file_path", v_path)
                    cb.setStyleSheet("color: white; padding-top: 2px;")
                    checkbox_refs.append(cb)
                    v_layout.addWidget(cb)

                info_layout = QVBoxLayout()
                info_layout.setSpacing(2)
                info_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                lbl_top = QLabel(f"<b style='color: white;'>{v_name[:25]}...</b><br><span style='color: #a0a0a0; font-size: 0.77em;'>{vid.get('FrameSize','N/A')} | {vid.get('Size','N/A')}</span>")
                lbl_top.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                lbl_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                clock_icon = resource_path(os.path.join("assets", "uisvg", "clock.svg")).replace('\\', '/')
                lbl_dur = QPushButton(f" {vid.get('Duration','N/A')}")
                lbl_dur.setIcon(QIcon(clock_icon))
                lbl_dur.setStyleSheet("color: #a0a0a0; font-size: 0.77em; border: none; text-align: center; background: transparent;")
                lbl_dur.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                lbl_dur.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                
                info_layout.addWidget(lbl_top)
                info_layout.addWidget(lbl_dur)
                
                info_container = QWidget()
                info_container.setLayout(info_layout)
                
                v_layout.addWidget(info_container)

                btn_del = QPushButton("Recycle Bin")
                btn_del.setStyleSheet("""
                    QPushButton { background-color: #a31515; color: white; border-radius: 4px; padding: 8px 12px; font-weight: bold; border: none; }
                    QPushButton:hover { background-color: #d13438; }
                """)
                btn_del.clicked.connect(lambda checked, p=v_path, w=vid_widget, gc=group_card, vl=videos_layout: self.delete_video_duplicate(p, w, gc, vl))

                v_layout.addWidget(lbl_info)
                v_layout.addWidget(btn_del)
                videos_layout.addWidget(vid_widget)

            card_layout.addWidget(videos_container)
            self.content_layout.addWidget(group_card)
            
            btn_ignore.clicked.connect(lambda checked, gc=group_card, g_items=items, cbs=checkbox_refs: self.mark_not_duplicates(gc, g_items, cbs))

    def mark_not_duplicates(self, group_card, group_items, checkboxes):
        db_folder = self.settings_dialog.db_path_input.text().strip()
        db_file = os.path.join(db_folder, "library.db")
        if not os.path.exists(db_file): return

        conn = self.settings_dialog.shared_conn
        cursor = conn.cursor()

        path_to_hash = {}
        cursor.execute("SELECT file_path, hash FROM Images")
        db_paths = {os.path.normcase(p): h for p, h in cursor.fetchall()}
        try:
            cursor.execute("SELECT file_path, hash FROM tagless")
            db_paths.update({os.path.normcase(p): h for p, h in cursor.fetchall()})
        except sqlite3.OperationalError:
            pass

        for item in group_items:
            norm_path = os.path.normcase(item['Path'])
            if norm_path in db_paths:
                path_to_hash[item['Path']] = db_paths[norm_path]

        all_paths = [item['Path'] for item in group_items if item['Path'] in path_to_hash]
        if len(all_paths) < 2:
            QMessageBox.warning(self, "Error", "Could not locate these videos in the database. Please rescan your library.")
            self.log_console.append("> Failed to mark exception: Database hash missing for videos.")
            return 

        pairs_to_ignore = []

        if not checkboxes:
            h1 = path_to_hash[all_paths[0]]
            h2 = path_to_hash[all_paths[1]]
            pairs_to_ignore.append(tuple(sorted((h1, h2))))
        else:
            selected_paths = []
            for cb in checkboxes:
                try:
                    if cb.isChecked():
                        selected_paths.append(cb.property("file_path"))
                except RuntimeError:
                    continue
            
            if not selected_paths:
                QMessageBox.warning(self, "Selection Required", "Please check the box next to the video(s) that are not duplicates.")
                return
                
            for sel_path in selected_paths:
                if sel_path not in path_to_hash: continue
                sel_hash = path_to_hash[sel_path]
                for other_path in all_paths:
                    if sel_path != other_path and other_path in path_to_hash:
                        other_hash = path_to_hash[other_path]
                        pairs_to_ignore.append(tuple(sorted((sel_hash, other_hash))))

        cursor.execute("CREATE TABLE IF NOT EXISTS IgnoredPairs (hash1 TEXT, hash2 TEXT, PRIMARY KEY (hash1, hash2))")
        for h1, h2 in set(pairs_to_ignore):
            cursor.execute("INSERT OR IGNORE INTO IgnoredPairs (hash1, hash2) VALUES (?, ?)", (h1, h2))
            
        conn.commit()

        if os.path.exists(self.output_json_path):
            try:
                with open(self.output_json_path, 'r', encoding='utf-8') as f:
                    groups = json.load(f)
                
                for group in groups:
                    group_paths = [img["Path"] for img in group.get("Items", [])]
                    if all(p in group_paths for p in [i['Path'] for i in group_items]):
                        if not checkboxes:
                            group["Items"] = [] 
                        else:
                            group["Items"] = [img for img in group["Items"] if img["Path"] not in selected_paths]
                
                groups = [g for g in groups if len(g.get("Items", [])) > 1]
                
                with open(self.output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(groups, f, indent=4)
            except Exception as e:
                self.log_console.append(f"> Live Pruning Error: {e}")

        group_card.setParent(None)
        group_card.deleteLater()
        
        self.clear_player_if_playing([item['Path'] for item in group_items])
            
        self.log_console.append("> Exception saved. These videos will be ignored in all future scans.")

    def delete_video_duplicate(self, file_path, widget_to_remove, group_card, videos_layout):
        reply = QMessageBox.question(self, "Confirm Delete", f"Move this video to the Recycle Bin?\n\n{os.path.basename(file_path)}", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.clear_player_if_playing([file_path])

                if os.path.exists(file_path): 
                    send2trash(file_path)
                
                if self.settings_dialog.shared_conn:
                    conn = self.settings_dialog.shared_conn
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM Images WHERE file_path = ?", (file_path,))
                    conn.commit()

                if os.path.exists(self.output_json_path):
                    with open(self.output_json_path, 'r', encoding='utf-8') as f:
                        groups = json.load(f)
                        
                    for group in groups:
                        group["Items"] = [item for item in group.get("Items", []) if item["Path"] != file_path]
                        
                    groups = [g for g in groups if len(g.get("Items", [])) > 1]
                    
                    with open(self.output_json_path, 'w', encoding='utf-8') as f:
                        json.dump(groups, f, indent=4)
                
                widget_to_remove.setParent(None)
                widget_to_remove.deleteLater()
                
                active_widgets = [videos_layout.itemAt(i).widget() for i in range(videos_layout.count()) if videos_layout.itemAt(i) and videos_layout.itemAt(i).widget()]
                if len(active_widgets) <= 1:
                    group_card.setParent(None)
                    group_card.deleteLater()
                    
                    remaining_paths = []
                    for w in active_widgets:
                        if hasattr(w, 'path'): remaining_paths.append(w.path)
                    self.clear_player_if_playing(remaining_paths)
                    
                    self.log_console.append("> Only 1 file remaining. Group resolved and removed from view.")
                elif len(active_widgets) == 2:
                    for w in active_widgets:
                        for child in w.findChildren(QCheckBox):
                            child.setParent(None)
                            child.deleteLater()
                
                self.log_console.append(f"> Deleted: {os.path.basename(file_path)}")
                
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete file: {e}")

    def clear_player_if_playing(self, paths):
        current_playing = self.media_player.source().toLocalFile()
        if not current_playing: return
        
        norm_playing = os.path.normcase(current_playing)
        norm_paths = [os.path.normcase(p) for p in paths]
        
        if norm_playing in norm_paths:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.media_player.setVideoOutput(None)
            self.media_player.setVideoOutput(self.video_widget)
            self.lbl_preview_title.setText("Video Player (Click a video to play)")