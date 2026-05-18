import os
import sys
import json
import sqlite3
import subprocess
import requests
import zipfile
from collections import defaultdict
from send2trash import send2trash

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QLabel, QScrollArea, QFrame, QSplitter, 
                             QMessageBox, QSlider, QProgressBar)
from PyQt6.QtCore import Qt, QProcess, QThread, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

# ==========================================
# CUSTOM UI ELEMENTS & WORKERS
# ==========================================

class ClickableFrame(QFrame):
    """A custom widget that acts like a button so we can click the whole video card."""
    clicked = pyqtSignal(str)
    
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit(self.path)
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
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                out, _ = process.communicate(timeout=5)
                if out:
                    self.result_ready.emit(path, out)
            except Exception:
                pass


# ==========================================
# 📥 DOWNLOAD WORKER (VDF + FFMPEG)
# ==========================================
class EngineDownloadThread(QThread):
    """Downloads both the VDF CLI engine and FFmpeg, extracts them, and cleans up."""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log_msg = pyqtSignal(str) # 🔹 Detailed console logging
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, extract_dir):
        super().__init__()
        self.extract_dir = extract_dir
        self.vdf_url = "https://github.com/0x90d/videoduplicatefinder/releases/download/3.0.x/CLI-win-x64.zip"
        self.ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

    def _download_file(self, url, dest_path, status_text):
        """Helper function to download a file and update the progress bar."""
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
            
            # --- 1. DOWNLOAD VDF ---
            vdf_zip = os.path.join(self.extract_dir, "vdf.zip")
            if not self._download_file(self.vdf_url, vdf_zip, "Downloading VDF Engine..."): return
            
            self.status.emit("Extracting VDF Engine...")
            self.log_msg.emit(f"> [SYSTEM] Unzipping VDF Engine into workspace...")
            with zipfile.ZipFile(vdf_zip, 'r') as zip_ref:
                zip_ref.extractall(self.extract_dir)
            os.remove(vdf_zip)
            self.log_msg.emit(f"  └─ Success! Removed temp zip: {vdf_zip}")

            # --- 2. DOWNLOAD FFMPEG ---
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
            self.log_msg.emit(f"  └─ Success! Removed temp zip: {ffmpeg_zip}")

            self.status.emit("Cleaning up...")
            self.log_msg.emit("> [SYSTEM] Installation routine completed successfully.")
            self.finished_signal.emit(True, "")
        except Exception as e:
            self.log_msg.emit(f"\n> [CRITICAL ERROR] Download failed: {str(e)}")
            self.finished_signal.emit(False, str(e))


# ==========================================
# MAIN TAB CLASS
# ==========================================

class VideoDedupTab(QWidget):
    def __init__(self, settings_dialog):
        super().__init__()
        self.settings_dialog = settings_dialog
        
        # CLI Process
        self.vdf_process = QProcess()
        self.vdf_process.readyReadStandardOutput.connect(self.handle_stdout)
        self.vdf_process.readyReadStandardError.connect(self.handle_stderr)
        self.vdf_process.finished.connect(self.process_finished)
                
        # 🔹 PATH RESOLUTION 🔹
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        self.engine_dir = os.path.join(app_dir, "Engine", "VideoDuplicateFinder")
        self.cli_path = os.path.join(self.engine_dir, "vdf-cli.exe")
        self.ffmpeg_path = os.path.join(self.engine_dir, "ffmpeg.exe") 
        self.output_json_path = "" 
        
        self.thumb_worker = ThumbnailWorker(self.ffmpeg_path)
        self.thumb_worker.result_ready.connect(self.apply_thumbnail)
        self.thumbnail_labels = {}
        
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. TOP CONTROL PANEL
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
        
        self.btn_scan = QPushButton("🎬 Start Video Scan")
        self.btn_scan.setFixedSize(170, 32)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet("""
            QPushButton { background-color: #8957e5; color: white; font-weight: bold; border-radius: 4px; border: none; } 
            QPushButton:hover:!disabled { background-color: #9d6ceb; }
        """)
        self.btn_scan.clicked.connect(self.start_cli_scan)
        
        self.btn_download = QPushButton("📥 Download VDF Engine")
        self.btn_download.setFixedSize(190, 32)
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; border: none; } 
            QPushButton:hover:!disabled { background-color: #0098ff; }
        """)
        self.btn_download.clicked.connect(self.download_engine)
        
        if os.path.exists(self.cli_path):
            self.btn_download.hide()
        
        self.lbl_status = QLabel("Ready to find exact duplicate videos.")
        self.lbl_status.setStyleSheet("color: #0e639c; font-weight: bold; border: none; margin-left: 10px;")

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

        # 2. SPLIT VIEW
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px; }")
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content_widget)
        splitter.addWidget(self.scroll_area)

        # RIGHT: Preview & Logs
        right_panel = QSplitter(Qt.Orientation.Vertical)
        
        # -- VIDEO PLAYER UI --
        self.preview_frame = QFrame()
        self.preview_frame.setStyleSheet("background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px;")
        preview_layout = QVBoxLayout(self.preview_frame)
        
        self.lbl_preview_title = QLabel("🔍 Video Player (Click a video to play)")
        self.lbl_preview_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffffff; border: none;")
        preview_layout.addWidget(self.lbl_preview_title)
        
        self.video_widget = QVideoWidget()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.5) 
        
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        
        preview_layout.addWidget(self.video_widget, 1)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(5, 5, 5, 5)
        
        self.btn_play = QPushButton("▶️ Play")
        self.btn_play.setStyleSheet("background-color: #3e3e42; color: white; border-radius: 4px; padding: 5px 12px; font-weight: bold;")
        self.btn_play.clicked.connect(self.media_player.play)
        
        self.btn_pause = QPushButton("⏸️ Pause")
        self.btn_pause.setStyleSheet("background-color: #3e3e42; color: white; border-radius: 4px; padding: 5px 12px; font-weight: bold;")
        self.btn_pause.clicked.connect(self.media_player.pause)

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.time_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3e3e42; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #8957e5; border-radius: 3px; }
            QSlider::handle:horizontal { background: white; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
            QSlider::handle:horizontal:hover { background: #d0d0d0; }
        """)
        
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #cccccc; font-size: 12px; font-weight: bold; font-family: Consolas;")

        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_pause)
        controls_layout.addWidget(self.time_slider, stretch=1)
        controls_layout.addWidget(self.lbl_time)
        
        preview_layout.addLayout(controls_layout)

        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.time_slider.sliderMoved.connect(self.media_player.setPosition)

        right_panel.addWidget(self.preview_frame)

        # -- LOGS --
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #0c0c0c; color: #cccccc; border: 1px solid #3e3e42; padding: 8px; border-radius: 4px; font-family: Consolas;")
        right_panel.addWidget(self.log_console)

        splitter.setSizes([600, 350])
        right_panel.setSizes([300, 300]) 
        splitter.addWidget(right_panel)
        main_layout.addWidget(splitter, 1)


    # ==========================================
    # 📥 ENGINE DOWNLOAD LOGIC
    # ==========================================
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
            self.lbl_status.setText("✅ Engine Installed Successfully!")
            self.btn_download.hide()
            QMessageBox.information(self, "Download Complete", "The Video Duplicate Finder engine has been successfully installed and is ready to use!")
        else:
            self.lbl_status.setText("❌ Download Failed.")
            QMessageBox.critical(self, "Download Error", f"Failed to download the engine:\n{msg}")


    # ==========================================
    # VIDEO PLAYBACK LOGIC
    # ==========================================
    @pyqtSlot(str)
    def play_video(self, file_path):
        self.lbl_preview_title.setText(f"▶️ Playing: {os.path.basename(file_path)}")
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.play()

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


    # ==========================================
    # CLI LOGIC
    # ==========================================
    def start_cli_scan(self):
        if not os.path.exists(self.cli_path) or not os.path.exists(self.ffmpeg_path):
            QMessageBox.critical(self, "Engines Missing", "Required engines are missing.\n\nPlease click the 'Download VDF Engine' button to install them before scanning.")
            return

        db_folder = self.settings_dialog.db_path_input.text().strip()
        db_file = os.path.join(db_folder, "library.db")
        if not os.path.exists(db_file):
            QMessageBox.critical(self, "Error", "Could not find library.db.")
            return
            
        self.output_json_path = os.path.join(db_folder, "vdf_results.json")

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT file_path FROM Images")
            all_files = [row[0] for row in cursor.fetchall() if row[0]]
        except sqlite3.OperationalError:
            cursor.execute("SELECT file_name FROM characters")
            all_files = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()

        video_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.wmv', '.m4v'}
        video_files = [f for f in all_files if os.path.splitext(f)[1].lower() in video_exts]

        if not video_files:
            self.lbl_status.setText("✅ No videos found in database!")
            return

        drive_groups = defaultdict(list)
        for path in video_files:
            if os.path.exists(path):
                directory = os.path.dirname(path)
                drive = os.path.splitdrive(directory)[0]
                drive_groups[drive].append(directory)

        include_folders = []
        for drive, dir_paths in drive_groups.items():
            common_root = os.path.commonpath(dir_paths)
            include_folders.append(common_root)

        if os.path.exists(self.output_json_path):
            try: os.remove(self.output_json_path)
            except: pass

        engine_folder = os.path.dirname(self.cli_path)
        try:
            subprocess.run(["taskkill", "/F", "/IM", "vdf-cli.exe"], capture_output=True, creationflags=0x08000000)
        except Exception:
            pass 

        cache_db1 = os.path.join(engine_folder, "ScannedFiles.db")
        cache_db2 = os.path.join(engine_folder, "ScannedFiles_new.db")
        for cache_file in [cache_db1, cache_db2]:
            if os.path.exists(cache_file):
                try: os.remove(cache_file)
                except Exception: pass

        args = [
            "scan-and-compare", "--output", self.output_json_path,
            "--format", "json", "--use-phash", "--percent", str(self.slider_sim.value())
        ]
        for folder in include_folders:
            args.extend(["--include", folder])

        self.btn_scan.setEnabled(False)
        self.lbl_status.setText("⏳ Scanning... Please wait.")
        self.log_console.clear()
        
        # 🔹 DETAILED SCAN LOGGING 🔹
        self.log_console.append("=========================================")
        self.log_console.append("🎥 VIDEO DEDUPLICATION SCAN INITIATED")
        self.log_console.append("=========================================")
        self.log_console.append(f"> Target Database: {db_file}")
        self.log_console.append(f"> VDF Engine Path: {self.cli_path}")
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
            if not line or "ETA " in line or "%]" in line: continue
            self.log_console.append(line)
            self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def handle_stderr(self):
        err_data = self.vdf_process.readAllStandardError().data().decode(errors='replace')
        lines = err_data.replace('\r', '\n').split('\n')
        for line in lines:
            line = line.strip()
            if not line or "ETA " in line or "%]" in line: continue
            
            crash_keywords = ["Unhandled exception", "System.IO.IOException", "ScannedFiles_new.db", "at System.", "at VDF.", "at Microsoft."]
            if any(keyword in line for keyword in crash_keywords): continue
                
            self.log_console.append(line)
            self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def process_finished(self, exit_code, exit_status):
        self.btn_scan.setEnabled(True)
        if os.path.exists(self.output_json_path):
            self.lbl_status.setText("✅ Scan Complete! Processing results...")
            self.log_console.append("\n> Scan Complete! Parsing JSON results...")
            self.parse_vdf_results()
        else:
            self.lbl_status.setText("❌ Scan Failed.")
            self.log_console.append(f"\n> [CRITICAL] Engine failed to write JSON. (Exit code {exit_code})")

    # ==========================================
    # PARSING & UI RENDERING
    # ==========================================
    def parse_vdf_results(self):
        if not os.path.exists(self.output_json_path):
            return

        try:
            with open(self.output_json_path, 'r', encoding='utf-8') as f:
                groups = json.load(f)
                
            if not groups:
                self.lbl_status.setText("✅ Library is clean! No exact copies found.")
                self.render_video_groups([])
                return

            self.log_console.append(f"> Found {len(groups)} duplicate groups. Rendering UI...")
            self.lbl_status.setText(f"⚠️ Found {len(groups)} exact duplicate groups.")
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
            
            header = QLabel(f"🎬 Exact Duplicate Group #{i+1} ({len(items)} videos)")
            header.setStyleSheet("font-weight: bold; color: #ffffff; border: none; font-size: 14px; padding-bottom: 5px;")
            card_layout.addWidget(header)

            videos_container = QWidget()
            videos_container.setStyleSheet("background: transparent; border: none;") 
            videos_layout = QHBoxLayout(videos_container)
            videos_layout.setContentsMargins(0,0,0,0)
            videos_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

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

                lbl_thumb = QLabel("⏳ Loading Thumbnail...")
                lbl_thumb.setFixedSize(220, 124) 
                lbl_thumb.setStyleSheet("background-color: #000000; border-radius: 4px; color: #888888; border: none;")
                lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.thumbnail_labels[v_path] = lbl_thumb 
                
                dur_str = vid.get('Duration', '00:00:00')
                try:
                    parts = dur_str.split('.')[0].split(':')
                    dur_sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                except:
                    dur_sec = 0
                
                self.thumb_worker.add_task(v_path, dur_sec)

                info_text = (
                    f"<b style='color: white;'>{v_name[:25]}...</b><br>"
                    f"<span style='color: #a0a0a0; font-size: 10px;'>"
                    f"📐 {vid.get('FrameSize','N/A')} | 💾 {vid.get('Size','N/A')}<br>"
                    f"⏱️ {vid.get('Duration','N/A')}"
                    f"</span>"
                )
                lbl_info = QLabel(info_text)
                lbl_info.setWordWrap(True)
                lbl_info.setStyleSheet("border: none; margin-top: 5px;")

                btn_del = QPushButton("🗑️ Recycle Bin")
                btn_del.setFixedHeight(30)
                btn_del.setStyleSheet("""
                    QPushButton { background-color: #a31515; color: white; border-radius: 4px; font-weight: bold; border: none; }
                    QPushButton:hover { background-color: #d13438; }
                """)
                btn_del.clicked.connect(lambda checked, p=v_path, w=vid_widget: self.delete_video_duplicate(p, w))

                v_layout.addWidget(lbl_thumb)
                v_layout.addWidget(lbl_info)
                v_layout.addWidget(btn_del)
                videos_layout.addWidget(vid_widget)

            card_layout.addWidget(videos_container)
            self.content_layout.addWidget(group_card)

    def delete_video_duplicate(self, file_path, widget_to_remove):
        reply = QMessageBox.question(self, "Confirm Delete", f"Move this video to the Recycle Bin?\n\n{os.path.basename(file_path)}", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.media_player.source().toLocalFile() == file_path:
                    self.media_player.stop()
                    self.media_player.setSource(QUrl())
                    self.lbl_preview_title.setText("🔍 Video Player (Click a video to play)")

                if os.path.exists(file_path): 
                    send2trash(file_path)
                
                db_folder = self.settings_dialog.db_path_input.text().strip()
                db_file = os.path.join(db_folder, "library.db")
                if os.path.exists(db_file):
                    conn = sqlite3.connect(db_file)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM Images WHERE file_path = ?", (file_path,))
                    conn.commit()
                    conn.close()
                
                widget_to_remove.setParent(None)
                widget_to_remove.deleteLater()
                self.log_console.append(f"> Deleted: {os.path.basename(file_path)}")
                
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete file: {e}")