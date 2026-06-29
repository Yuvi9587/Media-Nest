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
Image.MAX_IMAGE_PIXELS = None
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QGroupBox, QListWidget,
                             QFileDialog, QMessageBox, QCompleter, QListWidgetItem,
                             QSplitter, QSizePolicy, QApplication, QDialog,
                             QProgressBar, QRadioButton, QButtonGroup, QCheckBox,
                             QPlainTextEdit, QStackedWidget, QSlider, QStyledItemDelegate,
                             QStyle)
from PyQt6.QtCore import Qt, QStringListModel, QThread, pyqtSignal, QSize, QUrl, QTimer, QSettings, QRect, QPoint
from PyQt6.QtGui import QPixmap, QImageReader, QMovie, QIcon, QColor, QPainter, QFont
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
            lbl.setStyleSheet("color: #cccccc; font-size: 0.85em; font-weight: bold;")

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

# ── Namespace colour palette ────────────────────────────────────────────────
NS_COLORS = {
    'character': QColor('#c792ea'),   # purple
    'artist':    QColor('#82aaff'),   # blue
    'series':    QColor('#ffcb6b'),   # gold
    'general':   QColor('#c3e88d'),   # green
    'metadata':  QColor('#f78c6c'),   # orange
}
NS_BG = {
    'character': QColor(60, 30, 80, 160),
    'artist':    QColor(20, 50, 100, 160),
    'series':    QColor(80, 60, 10, 160),
    'general':   QColor(30, 70, 30, 160),
    'metadata':  QColor(90, 40, 10, 160),
}


class NsColorModel(QStringListModel):
    """QStringListModel that returns namespace-based foreground/background colours
    via Qt's standard data roles — works reliably even when a QSS stylesheet is set."""

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        # Raw stored value is always "ns:tagname"
        raw = super().data(index, Qt.ItemDataRole.DisplayRole) or ""
        ns = raw.split(':', 1)[0] if ':' in raw else 'general'

        if role == Qt.ItemDataRole.ForegroundRole:
            return NS_COLORS.get(ns, QColor('#cccccc'))

        if role == Qt.ItemDataRole.BackgroundRole:
            return NS_BG.get(ns, QColor(40, 40, 40, 180))

        # UserRole: return the raw "ns:tag" string for pathFromIndex
        if role == Qt.ItemDataRole.UserRole:
            return raw

        # DisplayRole: show a short badge prefix so the user can see the namespace
        if role == Qt.ItemDataRole.DisplayRole:
            if ':' in raw:
                ns_part, tag_part = raw.split(':', 1)
                return f"[{ns_part.upper()[:4]}]  {tag_part}"
            return raw

        return super().data(index, role)


class DbLookupCompleter(QCompleter):
    """Fast completer that queries AllTags.db directly on each keystroke (debounced).
    Never loads 1.6M tags into memory — returns only the top 25 matches."""

    def __init__(self, parent=None):
        self._result_model = NsColorModel()
        super().__init__(self._result_model, parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setFilterMode(Qt.MatchFlag.MatchContains)  # safe: model only has 25 items
        self.setMaxVisibleItems(12)

        self._alltags_db = None
        self._library_db = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)   # ms after last keystroke
        self._debounce.timeout.connect(self._do_lookup)
        self._last_term = ""

    def _apply_popup_style(self):
        popup = self.popup()
        if not popup:
            return
        popup.setStyleSheet("""
            QListView {
                background-color: #1e1e2e;
                border: 1px solid #44475a;
                border-radius: 6px;
                padding: 2px;
                outline: none;
                font-size: 9pt;
            }
            QListView::item {
                padding: 3px 6px;
                border-radius: 3px;
            }
            QListView::item:selected {
                background-color: #2a2d3e;
            }
            QScrollBar:vertical {
                background: #2a2d3e;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #44475a;
                border-radius: 3px;
            }
        """)

    def set_db_paths(self, alltags_db, library_db):
        self._alltags_db = alltags_db
        self._library_db = library_db

    def on_text_changed(self, text):
        """Call this from the widget's textChanged signal."""
        # Extract the last token (after the last comma)
        last = text.split(',')[-1].strip() if ',' in text else text.strip()
        # Strip namespace prefix for the DB search term
        term = last.split(':', 1)[1].strip() if ':' in last else last
        if len(term) < 2:
            self._result_model.setStringList([])
            return
        self._last_term = term
        self._debounce.start()

    def _do_lookup(self):
        term = self._last_term
        if len(term) < 2:
            return
        results = []
        tables_to_ns = [
            ('CharacterTags', 'character'),
            ('ArtistTags',    'artist'),
            ('SeriesTags',    'series'),
            ('GeneralTags',   'general'),
            ('MetadataTags',  'metadata'),
        ]
        # Query AllTags.db
        if self._alltags_db and os.path.exists(self._alltags_db):
            try:
                conn = sqlite3.connect(self._alltags_db)
                conn.execute("PRAGMA journal_mode=WAL;")
                cur = conn.cursor()
                for table, ns in tables_to_ns:
                    try:
                        cur.execute(f"SELECT name FROM {table} WHERE name LIKE ? LIMIT 5",
                                    (f'%{term}%',))
                        for (name,) in cur.fetchall():
                            results.append(f"{ns}:{name}")
                    except sqlite3.OperationalError:
                        pass
                conn.close()
            except Exception:
                pass
        # Also query library.db Tags for locally known tags not in AllTags.db
        if self._library_db and os.path.exists(self._library_db):
            try:
                conn = sqlite3.connect(self._library_db)
                conn.execute("PRAGMA journal_mode=WAL;")
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT tag_name, tag_type FROM Tags WHERE tag_name LIKE ? LIMIT 10",
                        (f'%{term}%',))
                    for (name, ns) in cur.fetchall():
                        ns = ns or 'general'
                        entry = f"{ns}:{name}"
                        if entry not in results:
                            results.append(entry)
                except sqlite3.OperationalError:
                    pass
                conn.close()
            except Exception:
                pass
        self._result_model.setStringList(results[:25])
        if results and self.widget():
            self.complete()

    def showPopup(self):
        super().showPopup()
        popup = self.popup()
        widget = self.widget()
        if popup and widget:
            global_pos = widget.mapToGlobal(QPoint(0, widget.height()))
            popup.move(global_pos)
            popup.setFixedWidth(max(widget.width(), 320))
            self._apply_popup_style()

    # --- multi-tag support ---
    def pathFromIndex(self, index):
        # The model's DisplayRole returns "[CHAR]  tagname" — we want the raw "character:tagname"
        raw = self._result_model.data(index, Qt.ItemDataRole.UserRole) or ""
        if not raw:
            # Fall back: reconstruct from display text
            display = super().pathFromIndex(index)
            # Strip "[XXXX]  " badge prefix if present
            import re
            display = re.sub(r'^\[[A-Z]+\]\s+', '', display)
            raw = display
        text = self.widget().text() if self.widget() else ""
        if ',' in text:
            prefix = text[:text.rfind(',') + 1]
            return prefix + " " + raw
        return raw

    def splitPath(self, path):
        if ',' in path:
            return [path.split(',')[-1].strip()]
        return [path.strip()]


# Keep old name as alias so nothing else breaks
MultiTagCompleter = DbLookupCompleter



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

        url = "https://sbhnjnojxqahzkymbddw.supabase.co/rest/v1/unapproved_queue"
        key = "sb_publishable_N21jEpddyr7iRUo_OmQbzQ_aJysn802"

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
        url = "https://sbhnjnojxqahzkymbddw.supabase.co/rest/v1/global_tags_archive"
        key = "sb_publishable_N21jEpddyr7iRUo_OmQbzQ_aJysn802"
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

                        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        cursor.execute("INSERT INTO tagless (hash, file_path, file_name, phash, file_size) VALUES (?, ?, ?, ?, ?)",
                                       (file_hash, file_path, file_name, phash_value, file_size))
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
        lbl.setStyleSheet("font-size: 1.1em; font-weight: bold;")
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


class TaglessInboxLoaderWorker(QThread):
    """Fetches tagless file records from the DB and validates paths off the main thread."""
    # (valid_rows, invalid_hashes) where valid_rows = [(file_name, file_path, file_hash), ...]
    finished = pyqtSignal(list, list)

    def __init__(self, library_db):
        super().__init__()
        self.library_db = library_db

    def run(self):
        valid_rows = []
        invalid_hashes = []
        try:
            conn = sqlite3.connect(self.library_db)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            # Deduplicate tagless table
            cursor.execute("""
                DELETE FROM tagless
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM tagless GROUP BY hash
                )
            """)
            conn.commit()

            cursor.execute("SELECT file_name, file_path, hash FROM tagless ORDER BY file_name ASC")
            rows = cursor.fetchall()
            conn.close()

            for file_name, file_path, file_hash in rows:
                if not file_path or not os.path.exists(file_path):
                    invalid_hashes.append(file_hash)
                else:
                    valid_rows.append((file_name, file_path, file_hash))
        except Exception:
            pass

        self.finished.emit(valid_rows, invalid_hashes)



class GlobalTagLoaderWorker(QThread):
    """Loads all tags from AllTags.db, library.db, and characters.db in the
    background so the main UI thread never freezes, even with 1.6M tags."""
    finished = pyqtSignal(list, set)   # (combined_list, known_gelbooru_chars)

    def __init__(self, library_db, characters_db, alltags_db):
        super().__init__()
        self.library_db = library_db
        self.characters_db = characters_db
        self.alltags_db = alltags_db

    def run(self):
        tag_dict = {}
        known_chars = set()

        def normalize_tag(t): return str(t).strip().lower().replace(" ", "_")
        def add_tag(name, ns):
            prio = {'character': 5, 'artist': 4, 'series': 3, 'metadata': 2, 'general': 1}
            if name not in tag_dict or prio.get(ns, 1) > prio.get(tag_dict.get(name, 'general'), 1):
                tag_dict[name] = ns

        # 1. library.db tags
        if os.path.exists(self.library_db):
            try:
                conn = sqlite3.connect(self.library_db)
                conn.execute("PRAGMA journal_mode=WAL;")
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT tag_name, tag_type FROM Tags")
                    for row in cursor.fetchall():
                        if row[0]: add_tag(normalize_tag(row[0]), row[1] if row[1] else 'general')
                except sqlite3.OperationalError:
                    cursor.execute("SELECT tag_name FROM Tags")
                    for row in cursor.fetchall():
                        if row[0]: add_tag(normalize_tag(row[0]), 'general')
                conn.close()
            except Exception:
                pass

        # 2. AllTags.db — the big one, done on background thread
        if os.path.exists(self.alltags_db):
            try:
                conn = sqlite3.connect(self.alltags_db)
                conn.execute("PRAGMA journal_mode=WAL;")
                cursor = conn.cursor()
                tables_to_ns = {
                    'CharacterTags': 'character',
                    'ArtistTags':    'artist',
                    'SeriesTags':    'series',
                    'GeneralTags':   'general',
                    'MetadataTags':  'metadata',
                }
                for table, ns in tables_to_ns.items():
                    try:
                        cursor.execute(f"SELECT name FROM {table}")
                        for (name,) in cursor.fetchall():
                            if name:
                                clean = normalize_tag(name)
                                add_tag(clean, ns)
                                if ns == 'character':
                                    known_chars.add(clean)
                    except sqlite3.OperationalError:
                        pass
                conn.close()
            except Exception:
                pass

        # 3. characters.db
        if os.path.exists(self.characters_db):
            try:
                conn = sqlite3.connect(self.characters_db)
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
                            for c_name, r_str in cursor.fetchall():
                                if c_name:
                                    cn = normalize_tag(c_name)
                                    add_tag(cn, 'character'); known_chars.add(cn)
                                if r_str:
                                    alias_part = str(r_str)
                                    if '=' in alias_part: alias_part = alias_part.split('=', 1)[1]
                                    for alias in alias_part.split(','):
                                        ca = normalize_tag(alias)
                                        if ca and ca not in known_chars:
                                            add_tag(ca, 'character'); known_chars.add(ca)
                        else:
                            cursor.execute(f"SELECT {col_name} FROM {target_table}")
                            for (c_name,) in cursor.fetchall():
                                if c_name:
                                    cn = normalize_tag(c_name)
                                    add_tag(cn, 'character'); known_chars.add(cn)
                conn.close()
            except Exception:
                pass

        def sort_key(item):
            name, ns = item
            ns_prio = {'character': 1, 'series': 2, 'artist': 3, 'metadata': 4, 'general': 5}
            return (ns_prio.get(ns, 99), name)

        combined = [f"{ns}:{name}" for name, ns in sorted(tag_dict.items(), key=sort_key)]
        self.finished.emit(combined, known_chars)


class CopyTagsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Copy Tags From...")
        self.setFixedSize(300, 300)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        
        layout = QVBoxLayout(self)
        
        top_layout = QHBoxLayout()
        lbl = QLabel("Select tag categories to copy:")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        top_layout.addWidget(lbl)
        
        btn_help = QPushButton("?")
        btn_help.setFixedSize(24, 24)
        btn_help.setStyleSheet("background-color: #3e3e42; color: white; border-radius: 12px; font-weight: bold; font-size: 14px;")
        btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_help.clicked.connect(self.show_help)
        top_layout.addWidget(btn_help)
        top_layout.addStretch()
        
        layout.addLayout(top_layout)
        
        self.cb_series = QCheckBox("Series (series:)")
        self.cb_chars = QCheckBox("Characters (character:)")
        self.cb_artist = QCheckBox("Artist (artist:)")
        self.cb_meta = QCheckBox("Metadata (metadata:)")
        self.cb_general = QCheckBox("General Tags")
        
        from PyQt6.QtCore import QSettings
        self.settings = QSettings("MediaNest", "AppConfig")
        
        s_series = self.settings.value("copy_tags_cb_series", True, type=bool)
        s_chars = self.settings.value("copy_tags_cb_chars", True, type=bool)
        s_artist = self.settings.value("copy_tags_cb_artist", True, type=bool)
        s_meta = self.settings.value("copy_tags_cb_meta", True, type=bool)
        s_general = self.settings.value("copy_tags_cb_general", True, type=bool)
        
        self.cb_series.setChecked(s_series)
        self.cb_chars.setChecked(s_chars)
        self.cb_artist.setChecked(s_artist)
        self.cb_meta.setChecked(s_meta)
        self.cb_general.setChecked(s_general)
        
        for cb in [self.cb_series, self.cb_chars, self.cb_artist, self.cb_meta, self.cb_general]:
            cb.setStyleSheet("font-size: 13px; padding: 5px;")
            layout.addWidget(cb)
            
        layout.addSpacing(10)
        
        shortcut_lbl = QLabel("Activation Shortcut:")
        shortcut_lbl.setStyleSheet("font-size: 13px;")
        
        from PyQt6.QtWidgets import QKeySequenceEdit
        from PyQt6.QtGui import QKeySequence
        
        self.shortcut_edit = QKeySequenceEdit(self)
        current_shortcut = self.settings.value("copy_tags_shortcut", "Ctrl+Shift+C", type=str)
        self.shortcut_edit.setKeySequence(QKeySequence(current_shortcut))
        
        shortcut_layout = QHBoxLayout()
        shortcut_layout.addWidget(shortcut_lbl)
        shortcut_layout.addWidget(self.shortcut_edit)
        
        layout.addLayout(shortcut_layout)
            
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start Copying")
        self.btn_start.setStyleSheet("background-color: #007acc; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #3e3e42; color: white; padding: 8px; border-radius: 4px;")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_start)
        
        layout.addStretch()
        layout.addLayout(btn_layout)

    def accept(self):
        new_shortcut = self.shortcut_edit.keySequence().toString()
        if new_shortcut:
            self.settings.setValue("copy_tags_shortcut", new_shortcut)
            
        self.settings.setValue("copy_tags_cb_series", self.cb_series.isChecked())
        self.settings.setValue("copy_tags_cb_chars", self.cb_chars.isChecked())
        self.settings.setValue("copy_tags_cb_artist", self.cb_artist.isChecked())
        self.settings.setValue("copy_tags_cb_meta", self.cb_meta.isChecked())
        self.settings.setValue("copy_tags_cb_general", self.cb_general.isChecked())
        
        super().accept()

    def show_help(self):
        from PyQt6.QtWidgets import QMessageBox
        help_text = (
            "<h3>How to use Copy From</h3>"
            "<p>This feature allows you to clone specific tags from one file onto many other files quickly.</p>"
            "<ol>"
            "<li>Select the tag categories you want to copy here.</li>"
            "<li>Click <b>Start Copying</b>.</li>"
            "<li>Click on the <b>Source</b> file in the grid that contains the tags you want to copy.</li>"
            "<li>Now, click on any other files in the grid to instantly paste those tags onto them!</li>"
            "</ol>"
            "<p><b>Example:</b> You have 5 pictures of Goku. Tag the first picture manually with <code>character:goku</code> and <code>series:dragon ball</code>. "
            "Then press your Activation Shortcut, click Start Copying, click the first picture, and then quickly click the other 4 pictures to instantly tag them all!</p>"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("Copy Tags Help")
        msg.setText(help_text)
        msg.setStyleSheet("background-color: #1e1e1e; color: white;")
        msg.exec()

    def get_selected_namespaces(self):
        ns = []
        if self.cb_series.isChecked(): ns.append('series:')
        if self.cb_chars.isChecked(): ns.append('character:')
        if self.cb_artist.isChecked(): ns.append('artist:')
        if self.cb_meta.isChecked(): ns.append('metadata:')
        if self.cb_general.isChecked(): 
            ns.append('general:')
            ns.append('')
        return ns

class TagCountDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        data = index.data(Qt.ItemDataRole.UserRole)
        if not data: return
        file_hash = data.get("hash")
        if not file_hash: return

        count = 0
        tag_manager = None
        
        p = self.parent()
        while p:
            if hasattr(p, 'pending_tag_changes'):
                tag_manager = p
                break
            p = p.parent()
            
        if tag_manager and file_hash in tag_manager.pending_tag_changes:
            count = len(tag_manager.pending_tag_changes[file_hash])
        else:
            count = data.get("tag_count", 0)

        if count <= 0: return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        badge_size = 22
        x = rect.right() - badge_size - 4
        y = rect.top() + 4

        painter.setBrush(QColor(0, 122, 204, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x, y, badge_size, badge_size)

        painter.setPen(QColor("white"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(x, y, badge_size, badge_size, Qt.AlignmentFlag.AlignCenter, str(count))
        painter.restore()

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

        self.copy_tags_mode = None 
        self.copy_tags_namespaces = []
        self.copy_tags_source_tags = []
        
        from PyQt6.QtGui import QShortcut, QKeySequence
        from PyQt6.QtCore import QSettings
        settings = QSettings("MediaNest", "AppConfig")
        current_shortcut = settings.value("copy_tags_shortcut", "Ctrl+Shift+C", type=str)
        self.shortcut_copy_tags = QShortcut(QKeySequence(current_shortcut), self)
        self.shortcut_copy_tags.activated.connect(self.start_copy_tags_workflow)
        
        self.shortcut_cancel_copy = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_cancel_copy.activated.connect(self.cancel_copy_tags_workflow)

        self.log_signal.connect(self.append_log_to_console)

        self.setup_ui()

        self.pending_thumbnails = {}
        self.thumbnail_map = {}
        self.pending_cloud_matches = {}
        self.pending_tag_changes = {}
        self.pending_renames = {}
        self._retiring_workers = []   # keeps old workers alive until their thread exits

        from Src.Logic.app import SingleThumbnailThread, VideoThumbnailer, NsTabExpander

        self._search_expander = NsTabExpander(self.search_bar, self)
        self.search_bar.installEventFilter(self._search_expander)

        self._add_tag_expander = NsTabExpander(self.input_add_tag, self)
        self.input_add_tag.installEventFilter(self._add_tag_expander)

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

    def start_copy_tags_workflow(self):
        if self.copy_tags_mode is not None:
            self.cancel_copy_tags_workflow()
            return
            
        dialog = CopyTagsDialog(self)
        if dialog.exec():
            from PyQt6.QtCore import QSettings
            from PyQt6.QtGui import QKeySequence
            settings = QSettings("MediaNest", "AppConfig")
            new_shortcut = settings.value("copy_tags_shortcut", "Ctrl+Shift+C", type=str)
            self.shortcut_copy_tags.setKey(QKeySequence(new_shortcut))
            
            if hasattr(self, 'btn_copy_tags'):
                self.btn_copy_tags.setToolTip(f"Activate Copy Mode to clone specific tags to other items. (Shortcut: {new_shortcut})")
            
            self.copy_tags_namespaces = dialog.get_selected_namespaces()
            if not self.copy_tags_namespaces:
                self.log("Copy mode cancelled: No namespaces selected.")
                return
                
            self.copy_tags_mode = "SELECT_SOURCE"
            from PyQt6.QtGui import QCursor, QPixmap
            cursor_pixmap = QPixmap(resource_path(os.path.join("assets", "uisvg", "cursor_source.svg")))
            self.inbox_list_widget.setCursor(QCursor(cursor_pixmap, 2, 2))
            if hasattr(self, 'btn_copy_tags'):
                self.btn_copy_tags.setText("Cancel (Esc)")
                self.btn_copy_tags.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; border-radius: 4px; padding: 5px; font-weight: bold; } QPushButton:hover { background-color: #f44336; }")
            self.log("COPY MODE ACTIVE: Click an item in the grid to select it as the SOURCE.")
            
    def cancel_copy_tags_workflow(self):
        if self.copy_tags_mode is not None:
            self.copy_tags_mode = None
            self.copy_tags_namespaces = []
            self.copy_tags_source_tags = []
            self.inbox_list_widget.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, 'btn_copy_tags'):
                self.btn_copy_tags.setText("Copy From")
                self.btn_copy_tags.setStyleSheet("QPushButton { background-color: #007acc; color: white; border-radius: 4px; padding: 5px; font-weight: bold; } QPushButton:hover { background-color: #0098ff; }")
            self.log("Copy Mode Cancelled.")

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
        from PyQt6.QtCore import QSettings
        hw_profile = QSettings("MediaNest", "AppConfig").value("hw_profile", "Balanced", type=str)
        if hw_profile == "Low-End":
            self.search_timer.setInterval(1500)
        elif hw_profile == "Balanced":
            self.search_timer.setInterval(800)
        else:
            self.search_timer.setInterval(350)
            
        self.search_timer.timeout.connect(self.search_library_by_tag)

        self.search_bar.textChanged.connect(self.search_timer.start)
        self.search_bar.returnPressed.connect(self.search_library_by_tag)
        self.search_completer = DbLookupCompleter()
        self.search_bar.setCompleter(self.search_completer)
        self.search_bar.textEdited.connect(self.search_completer.on_text_changed)
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
        self.inbox_list_widget.setItemDelegate(TagCountDelegate(self.inbox_list_widget))
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
        self.lbl_rename_error.setStyleSheet("color: #ff5252; font-weight: bold; font-size: 0.85em;")
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
        self.file_tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tag_list.customContextMenuRequested.connect(self.show_tag_context_menu)

        add_tag_layout = QHBoxLayout()
        add_tag_layout.setSpacing(8)

        self.input_add_tag = QLineEdit()
        self.input_add_tag.setFixedHeight(34)
        self.input_add_tag.setPlaceholderText("Add tag manually...")
        self.input_add_tag.setStyleSheet("border-radius: 4px; padding-left: 8px;")

        self.tag_completer = DbLookupCompleter()
        self.tag_completer.setMaxVisibleItems(12)
        self.input_add_tag.setCompleter(self.tag_completer)
        self.input_add_tag.textEdited.connect(self.tag_completer.on_text_changed)

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

        action_btn_layout = QHBoxLayout()

        self.btn_remove_file_tag = QPushButton("Delete")
        self.btn_remove_file_tag.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "remove.svg"))))
        self.btn_remove_file_tag.clicked.connect(self.delete_checked_tags)

        from PyQt6.QtCore import QSettings
        current_shortcut = QSettings("MediaNest", "AppConfig").value("copy_tags_shortcut", "Ctrl+Shift+C", type=str)
        
        self.btn_copy_tags = QPushButton("Copy From")
        self.btn_copy_tags.setToolTip(f"Activate Copy Mode to clone specific tags to other items. (Shortcut: {current_shortcut})")
        self.btn_copy_tags.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "copy.svg"))))
        self.btn_copy_tags.clicked.connect(self.start_copy_tags_workflow)
        self.btn_copy_tags.setStyleSheet("QPushButton { background-color: #007acc; color: white; border-radius: 4px; padding: 5px; font-weight: bold; } QPushButton:hover { background-color: #0098ff; }")
        self.btn_copy_tags.setCursor(Qt.CursorShape.PointingHandCursor)

        action_btn_layout.addWidget(self.btn_remove_file_tag)
        action_btn_layout.addWidget(self.btn_copy_tags)

        active_tags_layout.addWidget(self.file_tag_list)
        active_tags_layout.addLayout(add_tag_layout)
        active_tags_layout.addLayout(action_btn_layout)
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
        self.console.setStyleSheet("background-color: #0c0c0c; color: #4CAF50; font-family: Consolas, monospace; font-size: 0.85em; border: 1px solid #3e3e42; border-radius: 4px;")
        workspace_layout.addWidget(self.console, stretch=3)

        self.workspace_btn_layout = QHBoxLayout()

        self.btn_approve_all_cloud = QPushButton("Batch Approve All")
        self.btn_approve_all_cloud.setMinimumHeight(40)
        self.btn_approve_all_cloud.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_approve_all_cloud.setStyleSheet("QPushButton { background-color: #238636; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #2ea043; }")
        self.btn_approve_all_cloud.clicked.connect(self.batch_approve_all_cloud)
        self.btn_approve_all_cloud.hide()

        self.btn_save_archive = QPushButton("Save All Pending Changes")
        self.btn_save_archive.setMinimumHeight(40)
        self.btn_save_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
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
        self.cb_help_others.setStyleSheet("QCheckBox { color: #888; font-style: italic; font-size: 1em; }")

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

        item.setData(Qt.ItemDataRole.UserRole, {"path": file_path, "hash": file_hash, "tag_count": 0})
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

    def _retire_worker(self, worker):
        """Disconnect the worker's custom signal, keep the Python object alive until
        the OS thread actually exits, then drop the reference automatically."""
        try:
            worker.finished.disconnect()
        except Exception:
            pass
        self._retiring_workers.append(worker)
        # QThread emits its own built-in finished() when the OS thread is truly done
        worker.finished.connect(lambda: self._retiring_workers.remove(worker)
                                if worker in self._retiring_workers else None)
        worker.quit()

    def refresh_global_tags(self):
        library_db, characters_db = self.get_db_paths()

        appdata_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "appdata")
        os.makedirs(appdata_dir, exist_ok=True)
        alltags_db = os.path.join(appdata_dir, "AllTags.db")

        # Add Tag completer gets the full 1.6M database + local library
        self.tag_completer.set_db_paths(alltags_db, library_db)
        # Search Index completer ONLY gets the local library (no point suggesting tags that aren't on files)
        self.search_completer.set_db_paths("", library_db)

        # Retire any previous worker without blocking the main thread
        if hasattr(self, '_tag_loader') and self._tag_loader:
            self._retire_worker(self._tag_loader)

        self._tag_loader = GlobalTagLoaderWorker(library_db, characters_db, alltags_db)
        self._tag_loader.finished.connect(self._on_tags_loaded)
        self._tag_loader.start()

    def _on_tags_loaded(self, combined_list, known_chars):
        """Called on the main thread when the background loader finishes."""
        self.tag_completer_model.setStringList(combined_list)
        self.known_gelbooru_chars = known_chars

        # Give the live-lookup completers their DB paths so they can start working
        appdata_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "appdata")
        alltags_db = os.path.join(appdata_dir, "AllTags.db")
        library_db, _ = self.get_db_paths()
        
        self.tag_completer.set_db_paths(alltags_db, library_db)
        self.search_completer.set_db_paths("", library_db)

    def refresh_tagless_inbox(self):
        self.inbox_list_widget.clear()
        self.thumbnail_map.clear()
        self.thumb_worker.clear_queue()
        self.vid_thumb_worker.clear_queue()

        library_db, _ = self.get_db_paths()
        if not os.path.exists(library_db):
            return

        # Retire any previous loader without blocking the main thread
        if hasattr(self, '_inbox_loader') and self._inbox_loader:
            self._retire_worker(self._inbox_loader)

        self._inbox_loader = TaglessInboxLoaderWorker(library_db)
        self._inbox_loader.finished.connect(self._on_inbox_loaded)
        self._inbox_loader.start()

    def _on_inbox_loaded(self, valid_rows, invalid_hashes):
        """Called on the main thread; batch-adds inbox items to avoid a single-frame freeze."""
        # Clean up invalid hashes in library using shared conn
        if invalid_hashes:
            try:
                conn = self.settings_dialog.shared_conn
                cursor = conn.cursor()
                for h in invalid_hashes:
                    cursor.execute("DELETE FROM tagless WHERE hash = ?", (h,))
                conn.commit()
                self.log(f"[DB: library.db] Inbox Cleanup: Removed {len(invalid_hashes)} missing files.")
            except Exception as e:
                self.log(f"TAGLESS CLEANUP ERR: {e}")

        # Stop any previous batch timer BEFORE creating a new one
        if hasattr(self, '_inbox_batch_timer') and self._inbox_batch_timer is not None:
            self._inbox_batch_timer.stop()
            self._inbox_batch_timer.deleteLater()
            self._inbox_batch_timer = None

        if not valid_rows:
            self.log(f"[DB: library.db] Tagless Queue synchronized. (0 items)")
            return

        # Store rows so we can feed them in batches
        self._inbox_pending_rows = list(valid_rows)
        self._inbox_img_queue = []
        self._inbox_vid_queue = []

        # Use a timer to add items in batches of 50 so the UI stays responsive
        self._inbox_batch_timer = QTimer(self)
        self._inbox_batch_timer.setInterval(0)   # next event-loop tick
        self._inbox_batch_timer.timeout.connect(self._add_inbox_batch)
        self._inbox_batch_timer.start()

        self.log(f"[DB: library.db] Loading {len(valid_rows)} tagless items...")


    def _add_inbox_batch(self):
        """Adds up to 50 inbox items per event-loop tick so the UI never freezes."""
        BATCH = 50
        batch = self._inbox_pending_rows[:BATCH]
        self._inbox_pending_rows = self._inbox_pending_rows[BATCH:]

        empty_pixmap = QPixmap(150, 150)
        empty_pixmap.fill(Qt.GlobalColor.transparent)
        empty_icon = QIcon(empty_pixmap)

        for file_name, file_path, file_hash in batch:
            item = QListWidgetItem()
            item.setToolTip(file_name)
            item.setIcon(empty_icon)
            if file_hash in self.pending_tag_changes:
                item.setBackground(QColor(45, 125, 70, 100))
            item.setData(Qt.ItemDataRole.UserRole, {"path": file_path, "hash": file_hash, "tag_count": 0})
            self.thumbnail_map[file_path] = item
            self.inbox_list_widget.addItem(item)

            if any(file_name.lower().endswith(e) for e in ('.mp4', '.mkv', '.avi', '.webm', '.mov')):
                self._inbox_vid_queue.append(file_path)
            else:
                self._inbox_img_queue.append(file_path)

        if not self._inbox_pending_rows:
            # All done — kick off thumbnails
            self._inbox_batch_timer.stop()
            if self._inbox_img_queue:
                self.thumb_worker.add_to_queue(self._inbox_img_queue)
            if self._inbox_vid_queue:
                self.vid_thumb_worker.add_to_queue(self._inbox_vid_queue)
            self.log(f"[DB: library.db] Tagless Queue synchronized. ({self.inbox_list_widget.count()} items)")


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

        query = """
            SELECT i.hash, i.file_path, i.file_name, 
                   (SELECT COUNT(*) FROM ImageTags it WHERE it.hash = i.hash) as tag_count
            FROM Images i WHERE 
        """
        conditions = []
        params = []
        for tag in tags_to_search:
            ns = None
            if ':' in tag:
                prefix, val = tag.split(':', 1)
                prefix = prefix.strip().lower()
                if prefix in ['character', 'artist', 'series', 'metadata', 'general']:
                    ns = prefix
                    tag = val.strip()

            if ns:
                if not tag:
                    continue  # Prevent massive queries when user just autocompleted the namespace prefix
                conditions.append("""
                    hash IN (
                        SELECT it.hash
                        FROM ImageTags it
                        JOIN Tags t ON it.tag_id = t.tag_id
                        WHERE t.tag_name = ? AND t.tag_type = ?
                    )
                """)
                params.extend([tag, ns])
            else:
                conditions.append("""
                    hash IN (
                        SELECT it.hash
                        FROM ImageTags it
                        JOIN Tags t ON it.tag_id = t.tag_id
                        WHERE t.tag_name = ?
                    )
                """)
                params.append(tag)

        if not conditions:
            self.inbox_list_widget.clear()
            self.inbox_group.setTitle(f"Tag Management Index (Waiting for input...)")
            return

        query += " AND ".join(conditions)
        query += " ORDER BY tag_count ASC"
        cursor.execute(query, tuple(params))

        files_for_img_thumbs = []
        files_for_vid_thumbs = []

        for row in cursor.fetchall():
            file_hash, file_path, file_name, tag_count = row

            empty_pixmap = QPixmap(150, 150)
            empty_pixmap.fill(Qt.GlobalColor.transparent)

            item = QListWidgetItem()
            item.setToolTip(file_name)
            item.setIcon(QIcon(empty_pixmap))

            if file_hash in self.pending_tag_changes:
                item.setBackground(QColor(45, 125, 70, 100))

            item.setData(Qt.ItemDataRole.UserRole, {"path": file_path, "hash": file_hash, "tag_count": tag_count})
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
            for tag_data in self.pending_tag_changes[file_hash]:
                if isinstance(tag_data, tuple):
                    ns, tag_name = tag_data
                else:
                    ns, tag_name = 'general', tag_data
                display_text = f"[{ns.upper()[:4]}]  {tag_name}"
                item = QListWidgetItem(display_text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setForeground(NS_COLORS.get(ns, QColor('#cccccc')))
                item.setBackground(NS_BG.get(ns, QColor(40, 40, 40, 180)))
                item.setData(Qt.ItemDataRole.UserRole, {"tag_id": None, "tag_name": tag_name, "is_saved": False, "ns": ns})
                self.file_tag_list.addItem(item)

            self.btn_save_archive.setEnabled(True)
            self.btn_save_archive.setText("Save All Pending Changes")
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
            self.btn_approve_all_cloud.hide()

        else:
            library_db, _ = self.get_db_paths()
            if os.path.exists(library_db):
                conn = self.settings_dialog.shared_conn
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM tagless WHERE hash = ?", (file_hash,))
                is_in_tagless = cursor.fetchone() is not None
                cursor.execute("""
                    SELECT t.tag_id, t.tag_name, t.tag_type
                    FROM Tags t
                    JOIN ImageTags it ON t.tag_id = it.tag_id
                    WHERE it.hash = ?
                """, (file_hash,))

                for row in cursor.fetchall():
                    tag_id, tag_name, tag_type = row
                    ns = tag_type if tag_type else 'general'
                    display_text = f"[{ns.upper()[:4]}]  {tag_name}"
                    item = QListWidgetItem(display_text)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setForeground(NS_COLORS.get(ns, QColor('#cccccc')))
                    item.setBackground(NS_BG.get(ns, QColor(40, 40, 40, 180)))
                    item.setData(Qt.ItemDataRole.UserRole, {"tag_id": tag_id, "tag_name": tag_name, "is_saved": True, "ns": ns})
                    self.file_tag_list.addItem(item)

            if file_hash in self.pending_cloud_matches:
                for tag in self.pending_cloud_matches[file_hash]:
                    ns = 'general'
                    display_text = f"[{ns.upper()[:4]}]  {tag}"
                    item = QListWidgetItem(display_text)
                    item.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "cloud.svg"))))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setForeground(NS_COLORS.get(ns, QColor('#b388ff')))
                    item.setBackground(NS_BG.get(ns, QColor(40, 40, 40, 180)))
                    item.setData(Qt.ItemDataRole.UserRole, {"tag_id": None, "tag_name": tag, "is_saved": False, "ns": ns})
                    self.file_tag_list.addItem(item)

            if not is_in_tagless:
                self.btn_save_archive.setEnabled(False)
                self.btn_save_archive.setText("Already Archived")
                self.btn_save_archive.setStyleSheet("QPushButton { background-color: #2d2d2d; color: #666666; font-weight: bold; font-size: 1.1em; border-radius: 4px; border: 1px solid #3e3e42; }")
                self.btn_approve_all_cloud.hide()

            elif file_hash in self.pending_cloud_matches:
                self.btn_save_archive.setEnabled(True)
                self.btn_save_archive.setText("Approve Selected")
                self.btn_save_archive.setStyleSheet("QPushButton { background-color: #8957e5; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #9a68f6; }")
                self.btn_approve_all_cloud.show()

            else:
                self.btn_save_archive.setEnabled(True)
                self.btn_save_archive.setText("Save All Pending Changes")
                self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
                self.btn_approve_all_cloud.hide()


        self.lbl_tag_preview.set_image(file_path)

    def on_inbox_item_selected(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        file_path = data["path"]
        file_hash = data["hash"]
        
        if getattr(self, 'copy_tags_mode', None) == "SELECT_SOURCE":
            source_tags = []
            
            if file_hash in self.pending_tag_changes:
                for tag_data in self.pending_tag_changes[file_hash]:
                    if isinstance(tag_data, tuple):
                        ns, tag_name = tag_data
                    else:
                        ns, tag_name = 'general', tag_data
                    source_tags.append((ns, tag_name))
            else:
                library_db, _ = self.get_db_paths()
                if os.path.exists(library_db):
                    conn = self.settings_dialog.shared_conn
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT t.tag_name, t.tag_type
                        FROM Tags t
                        JOIN ImageTags it ON t.tag_id = it.tag_id
                        WHERE it.hash = ?
                    """, (file_hash,))
                    for row in cursor.fetchall():
                        tag_name, tag_type = row
                        ns = tag_type if tag_type else 'general'
                        source_tags.append((ns, tag_name))
            
            filtered_tags = []
            for ns, tag_name in source_tags:
                search_ns = ns + ":" if ns != 'general' else 'general:'
                # For empty namespace compatibility we also check ''
                if search_ns in self.copy_tags_namespaces or (ns == 'general' and '' in self.copy_tags_namespaces):
                    filtered_tags.append((ns, tag_name))
            
            if not filtered_tags:
                self.log("Source item has no tags matching the selected categories. Please select another source.")
                return
                
            self.copy_tags_source_tags = filtered_tags
            self.copy_tags_mode = "APPLY_TAGS"
            from PyQt6.QtGui import QCursor, QPixmap
            cursor_pixmap = QPixmap(resource_path(os.path.join("assets", "uisvg", "cursor_apply.svg")))
            self.inbox_list_widget.setCursor(QCursor(cursor_pixmap, 2, 2))
            self.log(f"Stored {len(filtered_tags)} tags from {os.path.basename(file_path)}. Click any target item to paste them.")
            return

        elif getattr(self, 'copy_tags_mode', None) == "APPLY_TAGS":
            if file_hash not in self.pending_tag_changes:
                self.pending_tag_changes[file_hash] = []
                library_db, _ = self.get_db_paths()
                if os.path.exists(library_db):
                    conn = self.settings_dialog.shared_conn
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT t.tag_name, t.tag_type
                        FROM Tags t
                        JOIN ImageTags it ON t.tag_id = it.tag_id
                        WHERE it.hash = ?
                    """, (file_hash,))
                    for row in cursor.fetchall():
                        t_name, t_type = row
                        ns = t_type if t_type else 'general'
                        
                        tag_tuple = (ns, t_name) if ns != 'general' else t_name
                        self.pending_tag_changes[file_hash].append(tag_tuple)

            added_count = 0
            for ns, tag_name in self.copy_tags_source_tags:
                tag_tuple = (ns, tag_name) if ns != 'general' else tag_name
                exists = False
                for existing in self.pending_tag_changes[file_hash]:
                    if isinstance(existing, tuple):
                        e_ns, e_name = existing
                    else:
                        e_ns, e_name = 'general', existing
                    if e_ns == ns and e_name == tag_name:
                        exists = True
                        break
                
                if not exists:
                    self.pending_tag_changes[file_hash].append(tag_tuple)
                    added_count += 1
            
            if added_count > 0:
                self.log(f"Pasted {added_count} tags to {os.path.basename(file_path)}.")
                item.setBackground(QColor(45, 125, 70, 100))
            else:
                self.log(f"All copied tags already exist in {os.path.basename(file_path)}.")
                
            self.load_file_into_tagger(file_path, file_hash)
            return

        self.load_file_into_tagger(file_path, file_hash)

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
            item = self.file_tag_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict) and "tag_name" in data:
                current_tags.append((data.get("ns", "general"), data["tag_name"]))
            else:
                # fallback for items added without data
                tag_text = item.text().replace("☁️ ", "").replace("☁️", "").strip()
                import re
                tag_text = re.sub(r'^\[[A-Z]+\]\s+', '', tag_text)
                if tag_text: current_tags.append(('general', tag_text))

        self.pending_tag_changes[self.current_file_hash] = current_tags

        if self.current_selected_file in self.thumbnail_map:
            item = self.thumbnail_map[self.current_selected_file]
            item.setBackground(QColor(45, 125, 70, 100))

        self.wake_up_save_button()

    def add_tag_to_current_list(self):
        raw_tag = self.input_add_tag.text().strip().lower().replace(" ", "_")
        if not raw_tag: return
        
        ns = 'general'
        tag_value = raw_tag
        if ":" in raw_tag:
            ns, tag_value = raw_tag.split(":", 1)
            ns = ns.strip()
            tag_value = tag_value.strip()

        display_text = f"[{ns.upper()[:4]}]  {tag_value}"

        existing_items = []
        for i in range(self.file_tag_list.count()):
            data = self.file_tag_list.item(i).data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict) and "tag_name" in data:
                existing_items.append(data["tag_name"])
            else:
                t = self.file_tag_list.item(i).text()
                t = t.replace("☁️ ", "").replace("☁️", "").strip()
                import re
                t = re.sub(r'^\[[A-Z]+\]\s+', '', t)
                existing_items.append(t)

        if tag_value not in existing_items:
            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setForeground(NS_COLORS.get(ns, QColor('#cccccc')))
            item.setBackground(NS_BG.get(ns, QColor(40, 40, 40, 180)))
            item.setData(Qt.ItemDataRole.UserRole, {"tag_id": None, "tag_name": tag_value, "is_saved": False, "ns": ns})
            self.file_tag_list.addItem(item)
            self.mark_current_file_changed()

        self.input_add_tag.clear()

    def filter_active_tags(self, text):
        search_text = text.lower()
        for i in range(self.file_tag_list.count()):
            item = self.file_tag_list.item(i)
            tag_name = item.text().lower()
            item.setHidden(search_text not in tag_name)

    def show_tag_context_menu(self, pos):
        item = self.file_tag_list.itemAt(pos)
        if not item: return
        
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #252526; color: white; border: 1px solid #3e3e42; } "
                           "QMenu::item { padding: 6px 24px 6px 24px; background: transparent; } "
                           "QMenu::item:selected { background-color: #007acc; }")
        
        change_cat_menu = menu.addMenu("Change Category...")
        
        cats = [("Series", "series"), ("Character", "character"), ("Artist", "artist"), ("Metadata", "metadata"), ("General", "general")]
        for display_name, ns in cats:
            action = change_cat_menu.addAction(display_name)
            action.triggered.connect(lambda checked, n=ns, i=item: self.change_tag_category(i, n))
            
        menu.exec(self.file_tag_list.mapToGlobal(pos))
        
    def change_tag_category(self, item, new_ns):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        
        old_ns = data.get("ns")
        tag_name = data.get("tag_name")
        if old_ns == new_ns: return
        
        if not self.current_file_hash: return
        
        if self.current_file_hash not in self.pending_tag_changes:
            self.pending_tag_changes[self.current_file_hash] = []
            
            library_db, _ = self.get_db_paths()
            if os.path.exists(library_db):
                conn = self.settings_dialog.shared_conn
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT t.tag_name, t.tag_type
                    FROM Tags t
                    JOIN ImageTags it ON t.tag_id = it.tag_id
                    WHERE it.hash = ?
                """, (self.current_file_hash,))
                for row in cursor.fetchall():
                    t_name, t_type = row
                    t_ns = t_type if t_type else 'general'
                    tag_tuple = (t_ns, t_name) if t_ns != 'general' else t_name
                    self.pending_tag_changes[self.current_file_hash].append(tag_tuple)
                    
        new_list = []
        for t in self.pending_tag_changes[self.current_file_hash]:
            t_str = t[1] if isinstance(t, tuple) else t
            if t_str.lower() != tag_name.lower():
                new_list.append(t)
        self.pending_tag_changes[self.current_file_hash] = new_list
            
        new_tuple = (new_ns, tag_name) if new_ns != 'general' else tag_name
        self.pending_tag_changes[self.current_file_hash].append(new_tuple)
        library_db, _ = self.get_db_paths()
        if os.path.exists(library_db):
            try:
                conn = self.settings_dialog.shared_conn
                cursor = conn.cursor()
                cursor.execute("UPDATE Tags SET tag_type = ? WHERE tag_name = ?", (new_ns, tag_name))
                conn.commit()
            except Exception as e:
                self.log(f"Error updating global database: {e}")
            
        self.load_file_into_tagger(self.current_selected_file, self.current_file_hash)
        self.log(f"Changed tag '{tag_name}' category to {new_ns.upper()} (Updated globally in Database).")

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
                if result.get("best_char"): new_tags.append(('character', result["best_char"].lower().replace(" ", "_")))

                for tag_name, score in result.get("top_tags", []):
                    if score >= 0.12:
                        new_tags.append(('general', tag_name.lower().replace(" ", "_")))

                new_tags = new_tags[:31]

                existing_items = []
                for i in range(self.file_tag_list.count()):
                    data = self.file_tag_list.item(i).data(Qt.ItemDataRole.UserRole)
                    if data and isinstance(data, dict) and "tag_name" in data:
                        existing_items.append(data["tag_name"])
                    else:
                        t = self.file_tag_list.item(i).text()
                        t = t.replace("☁️ ", "").replace("☁️", "").strip()
                        import re
                        t = re.sub(r'^\[[A-Z]+\]\s+', '', t)
                        existing_items.append(t)

                added_new_tags = False
                for ns, t in new_tags:
                    if t not in existing_items:
                        display_text = f"[{ns.upper()[:4]}]  {t}"
                        item = QListWidgetItem(display_text)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Unchecked)
                        item.setForeground(NS_COLORS.get(ns, QColor('#cccccc')))
                        item.setBackground(NS_BG.get(ns, QColor(40, 40, 40, 180)))
                        item.setData(Qt.ItemDataRole.UserRole, {"tag_id": None, "tag_name": t, "is_saved": False, "ns": ns})
                        self.file_tag_list.addItem(item)
                        added_new_tags = True

                if added_new_tags:
                    self.wake_up_save_button()
                    self.mark_current_file_changed()
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
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    cursor.execute("INSERT OR IGNORE INTO Images (hash, file_path, file_name, phash, file_size) VALUES (?, ?, ?, ?, ?)", (file_hash, file_path, file_name, phash_value, file_size))
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
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")

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
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")

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

                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                cursor.execute("INSERT OR IGNORE INTO Images (hash, file_path, file_name, phash, file_size) VALUES (?, ?, ?, ?, ?)", (file_hash, file_path, file_name, phash_value, file_size))

                cursor.execute("DELETE FROM ImageTags WHERE hash = ?", (file_hash,))

                for tag_data in tags:
                    if not tag_data: continue
                    if isinstance(tag_data, tuple):
                        ns, tag_name = tag_data
                    else:
                        ns, tag_name = 'general', tag_data

                    if not tag_name: continue
                    cursor.execute("INSERT OR IGNORE INTO Tags (tag_name, tag_type) VALUES (?, ?)", (tag_name, ns))
                    cursor.execute("SELECT tag_id FROM Tags WHERE tag_name = ?", (tag_name,))
                    tag_id = cursor.fetchone()[0]
                    cursor.execute("INSERT OR IGNORE INTO ImageTags (hash, tag_id) VALUES (?, ?)", (file_hash, tag_id))

                cursor.execute("DELETE FROM tagless WHERE hash = ?", (file_hash,))

                if tags and file_hash not in self.pending_cloud_matches:
                    # extract tag strings for cloud upload queue
                    tag_strs = [t[1] if isinstance(t, tuple) else t for t in tags]
                    upload_queue.append((file_hash, tag_strs))

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
            self.btn_save_archive.setStyleSheet("QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 4px; } QPushButton:hover { background-color: #0098ff; }")
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