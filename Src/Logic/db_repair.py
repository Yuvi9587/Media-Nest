import os
import sys
import hashlib
import sqlite3
import shutil
import datetime
from collections import Counter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QPlainTextEdit, QProgressBar, QFileDialog,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QCheckBox, QMessageBox, QSplitter, QFrame,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QSize
from PyQt6.QtGui import QColor, QFont, QIcon


def _svg(name) -> str:
    """Return absolute path to a uisvg asset."""
    base = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base, "assets", "uisvg", name)







class DbRepairWorker(QThread):
    log_signal      = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int, int)
    result_signal   = pyqtSignal(list, list)
    finished_signal = pyqtSignal()

    def __init__(self, library_db, scan_mode, target_path, match_mode):
        super().__init__()
        self.library_db  = library_db
        self.scan_mode   = scan_mode
        self.target_path = target_path
        self.match_mode  = match_mode
        self._abort      = False

    def abort(self):
        self._abort = True

    def _hash_file(self, path):
        """Compute MD5 hash of a file -- matches the algorithm used when importing into library.db."""
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return None

    def _get_broken_records(self):
        """Return list of (hash, file_path, file_name) whose paths don't exist."""
        conn = sqlite3.connect(self.library_db)
        conn.execute("PRAGMA journal_mode=WAL;")
        cur  = conn.cursor()
        cur.execute("SELECT hash, file_path, file_name FROM Images")
        rows = cur.fetchall()
        conn.close()
        return [(h, p, n) for h, p, n in rows if not os.path.exists(p)]

    def _get_surviving_ancestor(self, path):
        """Walk up the directory tree until an existing folder is found."""
        folder = os.path.dirname(path)
        while folder and not os.path.exists(folder):
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
        return folder if os.path.exists(folder) else None

    def _detect_smart_roots(self, broken_records):
        root_counts = Counter()
        drive_set   = set()
        for _, file_path, _ in broken_records:

            survivor = self._get_surviving_ancestor(file_path)
            if survivor:
                root_counts[survivor] += 1


            drive = os.path.splitdrive(file_path)[0]
            if drive:
                drive_set.add(drive.upper() + os.sep)


        smart_roots = [r for r, _ in root_counts.most_common()]


        for d in sorted(drive_set):
            if d not in smart_roots:
                smart_roots.append(d)


        import string
        for letter in string.ascii_uppercase:
            if letter == 'C':
                continue
            d = f"{letter}:\\"
            if os.path.exists(d) and d not in smart_roots:
                smart_roots.append(d)

        return smart_roots

    def _iter_scan_paths(self, broken_records):
        if self.scan_mode == "target":
            yield self.target_path
        else:
            for root in self._detect_smart_roots(broken_records):
                if os.path.isdir(root):
                    yield root

    def run(self):
        self.log_signal.emit("[SCAN] Loading broken records from library.db...", "#64b5f6")

        broken = self._get_broken_records()
        if not broken:
            self.log_signal.emit("[OK] No broken records found -- library looks healthy!", "#81c995")
            self.result_signal.emit([], [])
            self.finished_signal.emit()
            return

        self.log_signal.emit(f"[WARN] Found {len(broken)} missing file(s) in library.db", "#ffa726")

        by_name = {}
        by_hash = {}
        for h, old_path, file_name in broken:
            by_name.setdefault(file_name.lower(), []).append((h, old_path))
            by_hash[h] = (h, old_path, file_name)

        relocated = []
        resolved  = set()
        total_checked = 0

        for scan_root in self._iter_scan_paths(broken):
            if self._abort: break
            if not os.path.isdir(scan_root): continue

            self.log_signal.emit(f"[SCAN] Scanning: {scan_root}", "#64b5f6")

            for dirpath, dirnames, filenames in os.walk(scan_root):
                if self._abort: break

                dirnames[:] = [d for d in dirnames
                               if not d.startswith('.') and d.lower() not in (
                                   "$recycle.bin", "system volume information",
                                   "__pycache__", "venv", "venv312", "env", "node_modules"
                               )]

                if filenames:
                    self.log_signal.emit(f"  -> {dirpath}  ({len(filenames)} files)", "#888888")

                for fname in filenames:
                    if self._abort: break
                    full_path = os.path.join(dirpath, fname)
                    total_checked += 1
                    self.progress_signal.emit(total_checked, len(broken))

                    fname_lower = fname.lower()

                    if self.match_mode in ("filename", "both"):
                        candidates = by_name.get(fname_lower, [])
                        for h, old_path in candidates:
                            if h in resolved: continue
                            if self.match_mode == "filename":
                                relocated.append((h, old_path, full_path, "Filename"))
                                resolved.add(h)
                                self.log_signal.emit(
                                    f"  [FOUND] {os.path.basename(old_path)} -> {full_path}", "#81c995")
                            else:
                                computed = self._hash_file(full_path)
                                if computed and computed == h:
                                    relocated.append((h, old_path, full_path, "Hash+Filename"))
                                    resolved.add(h)
                                    self.log_signal.emit(
                                        f"  [CONFIRMED] {os.path.basename(old_path)} -> {full_path}", "#81c995")
                                elif candidates:
                                    self.log_signal.emit(
                                        f"  [WEAK] {fname} found but hash differs -- skipping", "#ffa726")

                    elif self.match_mode == "hash":
                        computed = self._hash_file(full_path)
                        if computed and computed in by_hash and computed not in resolved:
                            h, old_path, _ = by_hash[computed]
                            relocated.append((h, old_path, full_path, "Hash"))
                            resolved.add(h)
                            self.log_signal.emit(
                                f"  [HASH MATCH] {os.path.basename(old_path)} -> {full_path}", "#81c995")

        orphans = [(h, old_path, file_name)
                   for h, old_path, file_name in broken
                   if h not in resolved]

        if orphans:
            self.log_signal.emit(f"\n[MISS] {len(orphans)} file(s) could not be located:", "#ef5350")
            for h, old_path, file_name in orphans:
                self.log_signal.emit(f"     {file_name}  ({old_path})", "#888888")

        self.log_signal.emit(
            f"\n[DONE] Scan complete -- {len(relocated)} relocated, {len(orphans)} orphaned.", "#64b5f6")
        self.result_signal.emit(relocated, orphans)
        self.finished_signal.emit()






class DbRepairTab(QWidget):
    def __init__(self, settings_dialog, parent=None):
        super().__init__(parent)
        self.setObjectName("DbRepairGroup")
        self.settings_dialog = settings_dialog
        self.worker          = None
        self._backup_path    = None

        self._build_ui()


    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(8)


        title_row = QHBoxLayout()
        title_row.setContentsMargins(4, 0, 0, 0)
        title_row.setSpacing(8)

        title_icon = QLabel()
        title_icon.setPixmap(QIcon(_svg("wrench.svg")).pixmap(16, 16))

        title_label = QLabel("Database Repair")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #cccccc;")

        title_row.addWidget(title_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()
        root.addLayout(title_row)


        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3e3e42; margin-bottom: 4px;")
        line.setFixedHeight(1)
        root.addWidget(line)


        ctrl_row = QHBoxLayout()

        self.combo_scan_mode = QComboBox()
        self.combo_scan_mode.addItems(["Deep Scan (Smart)", "Target Folder / Drive"])
        self.combo_scan_mode.setToolTip(
            "Deep Scan: checks the most common file roots in your library first, then expands.\n"
            "Target: you pick a specific folder or drive to scan.")
        self.combo_scan_mode.currentIndexChanged.connect(self._on_mode_changed)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setIcon(QIcon(_svg("folder.svg")))
        self.btn_browse.setIconSize(QSize(14, 14))
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_target)
        self.btn_browse.hide()

        self.lbl_target = QLabel("(no folder selected)")
        self.lbl_target.setStyleSheet("color: #888;")
        self.lbl_target.hide()

        self.combo_match = QComboBox()
        self.combo_match.addItems([
            "Filename + Hash (Both -- Recommended)",
            "Filename Only (Fast)",
            "Hash Only (Thorough)"
        ])
        self.combo_match.setToolTip(
            "Both: matches by filename first, then verifies with full hash.\n"
            "Filename Only: fastest -- matches on name alone.\n"
            "Hash Only: computes MD5 of every file found (slow on large drives).")

        self.btn_start = QPushButton("Start Scan")
        self.btn_start.setIcon(QIcon(_svg("play.svg")))
        self.btn_start.setIconSize(QSize(14, 14))
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #007acc; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 6px 18px; border: none; } "
            "QPushButton:hover { background-color: #0098ff; } "
            "QPushButton:disabled { background-color: #3a3a3a; color: #666; }")
        self.btn_start.clicked.connect(self._start_scan)

        self.btn_abort = QPushButton("Stop")
        self.btn_abort.setIcon(QIcon(_svg("stop.svg")))
        self.btn_abort.setIconSize(QSize(14, 14))
        self.btn_abort.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_abort.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 6px 14px; border: none; } "
            "QPushButton:hover { background-color: #e74c3c; }")
        self.btn_abort.clicked.connect(self._abort_scan)
        self.btn_abort.hide()

        ctrl_row.addWidget(QLabel("Mode:"))
        ctrl_row.addWidget(self.combo_scan_mode)
        ctrl_row.addWidget(self.btn_browse)
        ctrl_row.addWidget(self.lbl_target)
        ctrl_row.addSpacing(20)
        ctrl_row.addWidget(QLabel("Match:"))
        ctrl_row.addWidget(self.combo_match)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.btn_start)
        ctrl_row.addWidget(self.btn_abort)
        root.addLayout(ctrl_row)


        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)


        h_splitter = QSplitter(Qt.Orientation.Horizontal)


        log_group = QGroupBox("")
        log_group.setObjectName("ScanLogGroup")
        log_inner = QVBoxLayout(log_group)
        log_inner.setContentsMargins(6, 6, 6, 6)

        log_title = QHBoxLayout()
        log_title.setContentsMargins(4, 0, 0, 4)
        log_icon = QLabel()
        log_icon.setPixmap(QIcon(_svg("log.svg")).pixmap(14, 14))
        log_lbl = QLabel("Scan Log")
        log_lbl.setStyleSheet("font-weight: bold; color: #cccccc;")
        log_title.addWidget(log_icon)
        log_title.addWidget(log_lbl)
        log_title.addStretch()
        log_inner.addLayout(log_title)

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        font = QFont("Consolas", 9)
        self.log_console.setFont(font)
        self.log_console.setStyleSheet(
            "QPlainTextEdit { background-color: #0c0c0c; color: #cccccc; "
            "border: 1px solid #3e3e42; border-radius: 4px; }")
        log_inner.addWidget(self.log_console)
        h_splitter.addWidget(log_group)


        v_splitter = QSplitter(Qt.Orientation.Vertical)


        self.relocated_group = QGroupBox("")
        rel_layout = QVBoxLayout(self.relocated_group)
        rel_layout.setContentsMargins(6, 6, 6, 6)

        rel_title = QHBoxLayout()
        rel_title.setContentsMargins(4, 0, 0, 4)
        rel_icon = QLabel()
        rel_icon.setPixmap(QIcon(_svg("folder.svg")).pixmap(14, 14))
        rel_lbl = QLabel("Relocated Files")
        rel_lbl.setStyleSheet("font-weight: bold; color: #e8a000;")
        rel_title.addWidget(rel_icon)
        rel_title.addWidget(rel_lbl)
        rel_title.addStretch()
        rel_layout.addLayout(rel_title)

        self.tbl_relocated = QTableWidget(0, 4)
        self.tbl_relocated.setHorizontalHeaderLabels(["File Name", "Old Path", "New Path", "Match"])
        self.tbl_relocated.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_relocated.horizontalHeader().setStretchLastSection(False)
        self.tbl_relocated.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_relocated.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_relocated.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_relocated.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_relocated.setStyleSheet(
            "QTableWidget { background-color: #1e1e1e; color: white; border: none; gridline-color: #3e3e42; } "
            "QHeaderView::section { background-color: #252526; color: #aaa; padding: 4px; border: none; }")
        rel_layout.addWidget(self.tbl_relocated)

        rel_action_row = QHBoxLayout()
        self.combo_fix_mode = QComboBox()
        self.combo_fix_mode.addItems([
            "Update Database  (point DB to new location)",
            "Move File Back   (restore file to original path)"
        ])
        self.combo_fix_mode.setToolTip(
            "Update Database: keeps the file where it is now -- updates library.db to match.\n"
            "Move File Back: physically moves the file back to the path the database expects.")
        self.combo_fix_mode.setEnabled(False)

        self.btn_apply_fixes = QPushButton("Apply All Fixes")
        self.btn_apply_fixes.setIcon(QIcon(_svg("check.svg")))
        self.btn_apply_fixes.setIconSize(QSize(14, 14))
        self.btn_apply_fixes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_fixes.setEnabled(False)
        self.btn_apply_fixes.setStyleSheet(
            "QPushButton { background-color: #238636; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 5px 16px; border: none; } "
            "QPushButton:hover { background-color: #2ea043; } "
            "QPushButton:disabled { background-color: #2d2d2d; color: #555; }")
        self.btn_apply_fixes.clicked.connect(self._apply_fixes)

        rel_action_row.addWidget(self.combo_fix_mode)
        rel_action_row.addWidget(self.btn_apply_fixes)
        rel_layout.addLayout(rel_action_row)
        v_splitter.addWidget(self.relocated_group)


        self.orphan_group = QGroupBox("")
        orp_layout = QVBoxLayout(self.orphan_group)
        orp_layout.setContentsMargins(6, 6, 6, 6)

        orp_title = QHBoxLayout()
        orp_title.setContentsMargins(4, 0, 0, 4)
        orp_icon = QLabel()
        orp_icon.setPixmap(QIcon(_svg("x_circle.svg")).pixmap(14, 14))
        orp_lbl = QLabel("Orphan Records (not found anywhere)")
        orp_lbl.setStyleSheet("font-weight: bold; color: #ef5350;")
        orp_title.addWidget(orp_icon)
        orp_title.addWidget(orp_lbl)
        orp_title.addStretch()
        orp_layout.addLayout(orp_title)

        self.tbl_orphans = QTableWidget(0, 3)
        self.tbl_orphans.setHorizontalHeaderLabels(["", "File Name", "Last Known Path"])
        self.tbl_orphans.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_orphans.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_orphans.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_orphans.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_orphans.setStyleSheet(
            "QTableWidget { background-color: #1e1e1e; color: white; border: none; gridline-color: #3e3e42; } "
            "QHeaderView::section { background-color: #252526; color: #aaa; padding: 4px; border: none; }")
        orp_layout.addWidget(self.tbl_orphans)

        orp_btn_row = QHBoxLayout()
        self.btn_select_all_orphans = QPushButton("Select All")
        self.btn_select_all_orphans.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all_orphans.setStyleSheet(
            "QPushButton { background-color: #3e3e42; color: white; border-radius: 4px; padding: 4px 12px; border: none; } "
            "QPushButton:hover { background-color: #505050; }")
        self.btn_select_all_orphans.clicked.connect(self._select_all_orphans)

        self.btn_delete_orphans = QPushButton("Delete Selected Orphans")
        self.btn_delete_orphans.setIcon(QIcon(_svg("trash.svg")))
        self.btn_delete_orphans.setIconSize(QSize(14, 14))
        self.btn_delete_orphans.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_orphans.setEnabled(False)
        self.btn_delete_orphans.setStyleSheet(
            "QPushButton { background-color: #6e1a1a; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 5px 16px; border: none; } "
            "QPushButton:hover { background-color: #c0392b; } "
            "QPushButton:disabled { background-color: #2d2d2d; color: #555; }")
        self.btn_delete_orphans.clicked.connect(self._delete_orphans)

        self.btn_recall_backup = QPushButton("Recall Backup")
        self.btn_recall_backup.setIcon(QIcon(_svg("refresh.svg")))
        self.btn_recall_backup.setIconSize(QSize(14, 14))
        self.btn_recall_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_recall_backup.setToolTip("Replaces library.db with the last backup taken before an orphan deletion.")
        self.btn_recall_backup.setStyleSheet(
            "QPushButton { background-color: #5a3e00; color: #ffd54f; font-weight: bold; "
            "border-radius: 4px; padding: 5px 16px; border: 1px solid #d29922; } "
            "QPushButton:hover { background-color: #7a5500; }")
        self.btn_recall_backup.clicked.connect(self._recall_backup)
        self.btn_recall_backup.hide()

        orp_btn_row.addWidget(self.btn_select_all_orphans)
        orp_btn_row.addWidget(self.btn_delete_orphans)
        orp_btn_row.addStretch()
        orp_btn_row.addWidget(self.btn_recall_backup)
        orp_layout.addLayout(orp_btn_row)
        v_splitter.addWidget(self.orphan_group)
        v_splitter.setSizes([300, 300])

        h_splitter.addWidget(v_splitter)
        h_splitter.setSizes([420, 580])
        root.addWidget(h_splitter, stretch=1)

        self._relocated_data = []
        self._orphan_data    = []



    def _on_mode_changed(self, idx):
        is_target = (idx == 1)
        self.btn_browse.setVisible(is_target)
        self.lbl_target.setVisible(is_target)

    def _browse_target(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder or Drive to Scan")
        if path:
            self.lbl_target.setText(path)
            self._target_path = path

    def _get_library_db(self):
        settings  = QSettings("MediaNest", "AppConfig")
        db_folder = settings.value("db_folder_path", "", type=str)
        return os.path.join(db_folder, "library.db")

    def _match_mode_key(self):
        idx = self.combo_match.currentIndex()
        return ["both", "filename", "hash"][idx]

    def _start_scan(self):
        library_db = self._get_library_db()
        if not os.path.exists(library_db):
            QMessageBox.warning(self, "No Database", "library.db not found. Check your Library Folder in Database Setup.")
            return

        scan_mode = "deep" if self.combo_scan_mode.currentIndex() == 0 else "target"
        if scan_mode == "target":
            target_path = getattr(self, "_target_path", "")
            if not target_path or not os.path.isdir(target_path):
                QMessageBox.warning(self, "No Folder Selected", "Please select a folder or drive to scan first.")
                return
        else:
            target_path = ""

        self.log_console.clear()
        self._relocated_data = []
        self._orphan_data    = []
        self._clear_tables()
        self.btn_apply_fixes.setEnabled(False)
        self.combo_fix_mode.setEnabled(False)
        self.btn_delete_orphans.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.btn_start.setEnabled(False)
        self.btn_abort.show()

        self.worker = DbRepairWorker(
            library_db  = library_db,
            scan_mode   = scan_mode,
            target_path = target_path,
            match_mode  = self._match_mode_key()
        )
        self.worker.log_signal.connect(self._append_log)
        self.worker.progress_signal.connect(self._update_progress)
        self.worker.result_signal.connect(self._on_results)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _abort_scan(self):
        if self.worker:
            self.worker.abort()

    def _append_log(self, message, color):
        safe = (message
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        self.log_console.appendHtml(f'<span style="color:{color};">{safe}</span>')
        sb = self.log_console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_progress(self, current, total):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def _on_results(self, relocated, orphans):
        self._relocated_data = relocated
        self._orphan_data    = orphans

        self.tbl_relocated.setRowCount(0)
        for h, old_path, new_path, match_type in relocated:
            row = self.tbl_relocated.rowCount()
            self.tbl_relocated.insertRow(row)
            self.tbl_relocated.setItem(row, 0, QTableWidgetItem(os.path.basename(old_path)))
            self.tbl_relocated.setItem(row, 1, QTableWidgetItem(old_path))
            self.tbl_relocated.setItem(row, 2, QTableWidgetItem(new_path))
            badge = QTableWidgetItem(match_type)
            badge.setForeground(QColor("#81c995") if "Hash" in match_type else QColor("#ffa726"))
            self.tbl_relocated.setItem(row, 3, badge)

        self.btn_apply_fixes.setEnabled(bool(relocated))
        self.combo_fix_mode.setEnabled(bool(relocated))

        self.tbl_orphans.setRowCount(0)
        for h, old_path, file_name in orphans:
            row = self.tbl_orphans.rowCount()
            self.tbl_orphans.insertRow(row)
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb.setCheckState(Qt.CheckState.Unchecked)
            cb.setData(Qt.ItemDataRole.UserRole, h)
            self.tbl_orphans.setItem(row, 0, cb)
            self.tbl_orphans.setItem(row, 1, QTableWidgetItem(file_name))
            path_item = QTableWidgetItem(old_path)
            path_item.setForeground(QColor("#888"))
            self.tbl_orphans.setItem(row, 2, path_item)

        self.btn_delete_orphans.setEnabled(bool(orphans))

    def _on_finished(self):
        self.progress_bar.hide()
        self.btn_start.setEnabled(True)
        self.btn_abort.hide()

    def _apply_fixes(self):
        if not self._relocated_data:
            return
        library_db = self._get_library_db()
        move_back  = (self.combo_fix_mode.currentIndex() == 1)
        ok_count   = 0
        fail_count = 0
        try:
            conn   = sqlite3.connect(library_db)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            for h, old_path, new_path, match_type in self._relocated_data:
                if move_back:
                    old_dir = os.path.dirname(old_path)
                    try:
                        os.makedirs(old_dir, exist_ok=True)
                        shutil.move(new_path, old_path)
                        self._append_log(
                            f"  [MOVED] {os.path.basename(new_path)} -> {old_path}", "#81c995")
                        ok_count += 1
                    except OSError as e:
                        self._append_log(
                            f"  [ERROR] Could not move {os.path.basename(new_path)}: {e}", "#ef5350")
                        fail_count += 1
                else:
                    new_name = os.path.basename(new_path)
                    cursor.execute(
                        "UPDATE Images SET file_path = ?, file_name = ? WHERE hash = ?",
                        (new_path, new_name, h))
                    cursor.execute(
                        "UPDATE tagless SET file_path = ?, file_name = ? WHERE hash = ?",
                        (new_path, new_name, h))
                    ok_count += 1
            conn.commit()
            conn.close()
            if move_back:
                self._append_log(
                    f"[OK] Moved {ok_count} file(s) back to original location(s)."
                    + (f"  {fail_count} failed." if fail_count else ""), "#81c995")
            else:
                self._append_log(
                    f"[OK] Updated {ok_count} database path(s) to new location(s).", "#81c995")
            self.btn_apply_fixes.setEnabled(False)
            self.combo_fix_mode.setEnabled(False)
            self._relocated_data = []
        except Exception as e:
            self._append_log(f"[ERROR] Error applying fixes: {e}", "#ef5350")

    def _select_all_orphans(self):
        for row in range(self.tbl_orphans.rowCount()):
            item = self.tbl_orphans.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _delete_orphans(self):
        selected_hashes = []
        for row in range(self.tbl_orphans.rowCount()):
            item = self.tbl_orphans.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_hashes.append(item.data(Qt.ItemDataRole.UserRole))

        if not selected_hashes:
            QMessageBox.information(self, "Nothing Selected", "Check the boxes next to the orphans you want to delete.")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"This will permanently remove {len(selected_hashes)} record(s) from library.db.\n"
            "A backup will be created first.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        library_db = self._get_library_db()

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = library_db + f".repair_backup_{stamp}.bak"
        try:
            shutil.copy2(library_db, backup_path)
            self._backup_path = backup_path
            self._append_log(f"[BACKUP] Saved: {backup_path}", "#64b5f6")
            self.btn_recall_backup.show()
        except Exception as e:
            self._append_log(f"[ERROR] Could not create backup: {e} -- aborting deletion.", "#ef5350")
            return

        try:
            conn   = sqlite3.connect(library_db)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            for h in selected_hashes:
                cursor.execute("DELETE FROM Images WHERE hash = ?",    (h,))
                cursor.execute("DELETE FROM ImageTags WHERE hash = ?", (h,))
                cursor.execute("DELETE FROM tagless WHERE hash = ?",   (h,))
            conn.commit()
            conn.close()
            self._append_log(f"[DELETED] Removed {len(selected_hashes)} orphan record(s) from library.db", "#ef5350")
            rows_to_remove = []
            for row in range(self.tbl_orphans.rowCount()):
                item = self.tbl_orphans.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) in selected_hashes:
                    rows_to_remove.append(row)
            for row in reversed(rows_to_remove):
                self.tbl_orphans.removeRow(row)
            self._orphan_data = [(h, p, n) for h, p, n in self._orphan_data if h not in selected_hashes]
            if not self._orphan_data:
                self.btn_delete_orphans.setEnabled(False)
        except Exception as e:
            self._append_log(f"[ERROR] Error during deletion: {e}", "#ef5350")

    def _recall_backup(self):
        if not self._backup_path or not os.path.exists(self._backup_path):
            QMessageBox.warning(self, "No Backup", "No backup file found for this session.")
            return
        reply = QMessageBox.question(
            self, "Restore Backup",
            f"This will replace your current library.db with:\n{self._backup_path}\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        library_db = self._get_library_db()
        try:
            shutil.copy2(self._backup_path, library_db)
            self._append_log(f"[RESTORED] library.db restored from backup successfully.", "#ffd54f")
            self.btn_recall_backup.hide()
            self._backup_path = None
        except Exception as e:
            self._append_log(f"[ERROR] Restore failed: {e}", "#ef5350")

    def _clear_tables(self):
        self.tbl_relocated.setRowCount(0)
        self.tbl_orphans.setRowCount(0)
