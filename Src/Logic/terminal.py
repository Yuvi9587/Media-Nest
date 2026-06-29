"""
Media-Nest Power Terminal
Full command suite — Basic to Advanced Power User.

Schema reference:
  Images(hash, file_path, file_name, phash)
  Tags(tag_id, tag_name)
  ImageTags(hash, tag_id)
  tagless(hash, file_path, file_name, phash)
  IgnoredPairs(hash1, hash2)
  Characters(character_name, gender, is_favorite, raw_string)
"""
import os
import re
import shlex
import sqlite3
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QLabel, QApplication, QMenu,
    QFrame, QPushButton
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QKeySequence, QShortcut, QTextDocument, QTextCursor


# ─────────────────────────────────────────────
#  Helper: parse --flag value from tokens
# ─────────────────────────────────────────────
def _parse_flags(tokens):
    """Return (positional_args, {flag: value}) from a token list.
    Supports  --flag value   and  --flag=value   and  bare --flag.
    """
    pos, flags = [], {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            key = tok.lstrip("-")
            if "=" in key:
                k, v = key.split("=", 1)
                flags[k] = v
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                flags[key] = tokens[i + 1]
                i += 1
            else:
                flags[key] = True        # bare flag
        else:
            pos.append(tok)
        i += 1
    return pos, flags


# ─────────────────────────────────────────────
#  Terminal Spinner
# ─────────────────────────────────────────────
class TerminalSpinner:
    """A small animated spinner to indicate long-running tasks."""
    def __init__(self, label):
        self.label = label
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.idx = 0
        self.active = False
        self.label.setText("")

    def start(self):
        self.active = True
        self.idx = 0
        self.label.setText(f"<span style='color:#00bcd4;'>{self.frames[0]}</span> ")
        QApplication.processEvents()

    def step(self):
        if not self.active: return
        self.idx = (self.idx + 1) % len(self.frames)
        self.label.setText(f"<span style='color:#00bcd4;'>{self.frames[self.idx]}</span> ")
        QApplication.processEvents()

    def stop(self):
        self.active = False
        self.label.setText("")
        QApplication.processEvents()


# ─────────────────────────────────────────────
#  The Terminal Widget
# ─────────────────────────────────────────────
class TerminalDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.db = db_manager
        self.setWindowTitle("Media-Nest Power Terminal")
        self.resize(920, 580)
        self.setStyleSheet("background-color: #0c0c0c; color: #cccccc;")

        # State
        self.history: list[str] = []
        self.history_idx = -1
        self.pending_confirmation = None   # (func, args) waiting for Y/N

        # ── Layout ──────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(0)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        # Allow text selection and copying in the read-only output area
        self.output.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.output.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.output.customContextMenuRequested.connect(self._output_context_menu)
        self.output.setStyleSheet("""
            QTextEdit {
                background-color: #0c0c0c;
                border: none;
                font-family: Consolas, "Lucida Console", monospace;
                font-size: 14px;
                padding: 6px;
            }
        """)
        root.addWidget(self.output)

        # Floating Search Bar
        self.search_frame = QFrame(self.output)
        self.search_frame.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333; border-radius: 4px;")
        search_layout = QHBoxLayout(self.search_frame)
        search_layout.setContentsMargins(4, 4, 4, 4)
        search_layout.setSpacing(6)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find...")
        self.search_input.setStyleSheet("background-color: #2c2c2c; color: #ffffff; padding: 4px; border: none; border-radius: 2px;")
        self.search_input.returnPressed.connect(self._search_next)
        self.search_input.installEventFilter(self)
        
        btn_prev = QPushButton("↑")
        btn_prev.setFixedSize(28, 28)
        btn_prev.setStyleSheet("QPushButton { background-color: #3c3c3c; color: white; border-radius: 2px; border: none; font-weight: bold; padding: 0px; text-align: center; } QPushButton:hover { background-color: #4c4c4c; }")
        btn_prev.clicked.connect(self._search_prev)
        
        btn_next = QPushButton("↓")
        btn_next.setFixedSize(28, 28)
        btn_next.setStyleSheet("QPushButton { background-color: #3c3c3c; color: white; border-radius: 2px; border: none; font-weight: bold; padding: 0px; text-align: center; } QPushButton:hover { background-color: #4c4c4c; }")
        btn_next.clicked.connect(self._search_next)
        
        btn_close = QPushButton("X")
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet("QPushButton { background-color: transparent; color: #aaa; border-radius: 2px; border: none; font-weight: bold; padding: 0px; text-align: center; } QPushButton:hover { color: white; background-color: #e81123; }")
        btn_close.clicked.connect(self._close_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_prev)
        search_layout.addWidget(btn_next)
        search_layout.addWidget(btn_close)
        
        self.search_frame.hide()

        # Search state
        self._last_search_term = ""

        inp_row = QHBoxLayout()
        inp_row.setContentsMargins(0, 0, 0, 0)

        self.prompt_label = QLabel("Media-Nest> ")
        self.prompt_label.setStyleSheet(
            "color: #cccccc; font-family: Consolas, \"Lucida Console\", monospace;"
            " font-size: 14px;"
        )

        self.spinner_label = QLabel("")
        self.spinner_label.setStyleSheet("font-family: Consolas; font-size: 14px; font-weight: bold; padding-left: 5px;")
        self.spinner = TerminalSpinner(self.spinner_label)

        self.input_line = QLineEdit()
        self.input_line.setStyleSheet("""
            QLineEdit {
                background-color: #0c0c0c;
                border: none;
                color: #cccccc;
                font-family: Consolas, "Lucida Console", monospace;
                font-size: 14px;
                padding: 5px 0px;
            }
        """)
        self.input_line.returnPressed.connect(self.process_command)
        self.input_line.installEventFilter(self)
        # Right-click context menu on input
        self.input_line.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.input_line.customContextMenuRequested.connect(self._input_context_menu)

        inp_row.addWidget(self.spinner_label)
        inp_row.addWidget(self.prompt_label)
        inp_row.addWidget(self.input_line)
        root.addLayout(inp_row)

        # Keyboard shortcut: Ctrl+Shift+C copies the entire output log
        sc = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        sc.activated.connect(self._copy_all_output)
        
        # Keyboard shortcut: Ctrl+F to find
        sc_find = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_find.activated.connect(self._show_search)
        
        # Keyboard shortcut: F3 to find next
        sc_find_next = QShortcut(QKeySequence("F3"), self)
        sc_find_next.activated.connect(self._search_next)

        # ── Boot message ─────────────────────────
        self._boot()

    # ─────────────────────────────────────────
    #  Boot banner
    # ─────────────────────────────────────────
    def _boot(self):
        self.print_msg("Media-Nest Power Terminal  [Version 2.0.0]", "#cccccc")
        self.print_msg("(c) Media-Nest Corporation.  All rights reserved.", "#cccccc")
        self.print_msg("")
        self.print_msg("Type  <b>help</b>  to list all commands.", "#00bcd4")
        self.print_msg("")

        # Set up SQLite progress handler to keep UI alive during heavy queries
        # (fires every 1000 SQLite VM instructions)
        try:
            self.db.set_progress_handler(self._sqlite_progress, 1000)
        except AttributeError:
            pass # fallback if db doesn't support it

    def _sqlite_progress(self):
        """Called automatically by SQLite during long queries."""
        if self.spinner.active:
            self.spinner.step()
        else:
            QApplication.processEvents()
        return 0

    # ─────────────────────────────────────────
    #  Search Features
    # ─────────────────────────────────────────
    def _show_search(self):
        w, h = 280, 40
        self.search_frame.setGeometry(self.output.width() - w - 25, 10, w, h)
        self.search_frame.show()
        self.search_frame.raise_()
        self.search_input.setFocus()
        self.search_input.selectAll()
        
    def _close_search(self):
        self.search_frame.hide()
        self.input_line.setFocus()
        cursor = self.output.textCursor()
        cursor.clearSelection()
        self.output.setTextCursor(cursor)
        
    def _search_next(self):
        term = self.search_input.text()
        if not term:
            return
        if not self.output.find(term):
            # Wrap around to start
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.output.setTextCursor(cursor)
            self.output.find(term)
            
    def _search_prev(self):
        term = self.search_input.text()
        if not term:
            return
        if not self.output.find(term, QTextDocument.FindFlag.FindBackward):
            # Wrap around to end
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.output.setTextCursor(cursor)
            self.output.find(term, QTextDocument.FindFlag.FindBackward)

    # ─────────────────────────────────────────
    #  Print helpers
    # ─────────────────────────────────────────
    def print_msg(self, msg, color="#cccccc"):
        from PyQt6.QtGui import QTextCursor
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Insert a newline before every line except the very first
        if not self.output.document().isEmpty():
            cursor.insertHtml("<br>")
        cursor.insertHtml(f"<span style='color:{color}; font-family:Consolas,\"Lucida Console\",monospace; font-size:14px;'>{msg}</span>")
        self.output.setTextCursor(cursor)
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def print_ok(self, msg):   self.print_msg(msg, "#4caf50")
    def print_err(self, msg):  self.print_msg(f"ERROR: {msg}", "#f44336")
    def print_warn(self, msg): self.print_msg(msg, "#ff9800")
    def print_info(self, msg): self.print_msg(msg, "#00bcd4")
    def print_dim(self, msg):  self.print_msg(msg, "#808080")

    # ─────────────────────────────────────────
    #  Context menus & clipboard helpers
    # ─────────────────────────────────────────
    _MENU_STYLE = """
        QMenu {
            background-color: #1e1e1e;
            border: 1px solid #454545;
            color: #cccccc;
            font-family: Consolas, "Lucida Console", monospace;
            font-size: 13px;
        }
        QMenu::item:selected { background-color: #3a3a5c; }
        QMenu::separator { height: 1px; background: #454545; margin: 2px 0; }
    """

    def _output_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(self._MENU_STYLE)

        has_selection = bool(self.output.textCursor().selectedText())

        act_copy = menu.addAction("Copy  \tCtrl+C")
        act_copy.setEnabled(has_selection)
        act_copy.triggered.connect(self.output.copy)

        menu.addSeparator()

        act_sel_all = menu.addAction("Select All  \tCtrl+A")
        act_sel_all.triggered.connect(self.output.selectAll)

        act_copy_all = menu.addAction("Copy All Output  \tCtrl+Shift+C")
        act_copy_all.triggered.connect(self._copy_all_output)

        menu.addSeparator()

        act_clear = menu.addAction("Clear Terminal")
        act_clear.triggered.connect(self.output.clear)

        menu.exec(self.output.mapToGlobal(pos))

    def _input_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(self._MENU_STYLE)

        has_selection = bool(self.input_line.selectedText())
        clipboard = QApplication.clipboard()
        has_clipboard = bool(clipboard.text())

        act_cut = menu.addAction("Cut  \tCtrl+X")
        act_cut.setEnabled(has_selection)
        act_cut.triggered.connect(self.input_line.cut)

        act_copy = menu.addAction("Copy  \tCtrl+C")
        act_copy.setEnabled(has_selection)
        act_copy.triggered.connect(self.input_line.copy)

        act_paste = menu.addAction("Paste  \tCtrl+V")
        act_paste.setEnabled(has_clipboard)
        act_paste.triggered.connect(self.input_line.paste)

        menu.addSeparator()

        act_sel_all = menu.addAction("Select All  \tCtrl+A")
        act_sel_all.triggered.connect(self.input_line.selectAll)

        menu.addSeparator()

        act_clear_input = menu.addAction("Clear Input")
        act_clear_input.triggered.connect(self.input_line.clear)

        menu.exec(self.input_line.mapToGlobal(pos))

    def _copy_all_output(self):
        """Copy the entire terminal output (as plain text) to clipboard."""
        text = self.output.toPlainText()
        QApplication.clipboard().setText(text)
        self.print_dim("[Copied all terminal output to clipboard]")


    # ─────────────────────────────────────────
    #  Key history navigation & Events
    # ─────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'search_frame') and self.search_frame.isVisible():
            w, h = 280, 40
            self.search_frame.setGeometry(self.output.width() - w - 25, 10, w, h)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress:
            if obj is getattr(self, "search_input", None) and event.key() == Qt.Key.Key_Escape:
                self._close_search()
                return True
                
        if obj is getattr(self, "input_line", None) and event.type() == event.Type.KeyPress:
            k = event.key()
            if k == Qt.Key.Key_Up:
                if self.history and self.history_idx < len(self.history) - 1:
                    self.history_idx += 1
                    self.input_line.setText(
                        self.history[len(self.history) - 1 - self.history_idx]
                    )
                return True
            if k == Qt.Key.Key_Down:
                if self.history_idx > 0:
                    self.history_idx -= 1
                    self.input_line.setText(
                        self.history[len(self.history) - 1 - self.history_idx]
                    )
                elif self.history_idx == 0:
                    self.history_idx = -1
                    self.input_line.clear()
                return True
            if k == Qt.Key.Key_Tab:
                self._autocomplete()
                return True
        return super().eventFilter(obj, event)

    def _autocomplete(self):
        """Very basic prefix autocomplete from history."""
        prefix = self.input_line.text()
        for cmd in reversed(self.history):
            if cmd.startswith(prefix) and cmd != prefix:
                self.input_line.setText(cmd)
                return

    # ─────────────────────────────────────────
    #  Command dispatcher
    # ─────────────────────────────────────────
    def process_command(self):
        raw = self.input_line.text().strip()
        if not raw:
            return
        self.input_line.clear()
        self.print_msg(f"Media-Nest&gt; {raw}", "#cccccc")

        # Record history (no duplicates at top)
        if not self.history or self.history[-1] != raw:
            self.history.append(raw)
        self.history_idx = -1

        # Pending Y/N confirmation
        if self.pending_confirmation:
            if raw.lower() in ("y", "yes"):
                fn, args, kwargs = self.pending_confirmation
                self.pending_confirmation = None
                try:
                    fn(*args, **kwargs)
                except Exception as exc:
                    self.print_err(str(exc))
            else:
                self.pending_confirmation = None
                self.print_dim("Aborted.")
            return

        # Parse tokens, escaping backslashes so Windows paths aren't destroyed
        try:
            tokens = shlex.split(raw.replace("\\", "\\\\"))
        except ValueError as exc:
            self.print_err(f"Syntax: {exc}")
            return

        if not tokens:
            return

        cmd = tokens[0].lower()
        args = tokens[1:]

        dispatch = {
            # ── BASIC ──
            "help":      self.cmd_help,
            "clear":     lambda _: self.output.clear(),
            "schema":    self.cmd_schema,
            "history":   self.cmd_history,
            "version":   self.cmd_version,

            # ── LIBRARY INFO ──
            "stats":     self.cmd_stats,
            "count":     self.cmd_count,
            "ls":        self.cmd_ls,
            "find":      self.cmd_find,
            "biggest":   self.cmd_biggest,
            "smallest":  self.cmd_smallest,
            "orphans":   self.cmd_orphans,
            "tagless":   self.cmd_tagless_list,
            "recent":    self.cmd_recent,
            "ext":       self.cmd_ext,

            # ── TAG COMMANDS ──
            "tag":       self.cmd_tag,

            # ── MANGA COMMANDS ──
            "manga":     self.cmd_manga,

            # ── FILE COMMANDS ──
            "file":      self.cmd_file,

            # ── DB COMMANDS ──
            "db":        self.cmd_db,
            "sql":       lambda _: self.cmd_sql(raw[4:]),

            # ── ADVANCED ──
            "dupes":     self.cmd_dupes,
            "export":    self.cmd_export,
            "scan":      self.cmd_scan,
        }

        handler = dispatch.get(cmd)
        if handler:
            self.spinner.start()
            try:
                if cmd == "sql":
                    handler(args)
                elif cmd == "clear":
                    handler(args)
                else:
                    handler(args)
            except Exception as exc:
                self.print_err(str(exc))
            finally:
                self.spinner.stop()
        else:
            self.print_err(f"Unknown command '{cmd}'. Type 'help' for a list.")

    # ═════════════════════════════════════════
    #  BASIC COMMANDS
    # ═════════════════════════════════════════

    def cmd_help(self, args=None):
        sections = [
            ("BASIC", [
                ("help [command]",   "Show this help.  Pass a command name for detailed usage."),
                ("clear",            "Clear the terminal output."),
                ("version",          "Show terminal version."),
                ("history",          "Print command history."),
                ("schema",           "Show all database tables and columns."),
            ]),
            ("LIBRARY INFO", [
                ("stats",                 "Overall library statistics."),
                ("count [--tag &lt;t&gt;]",  "Count files, optionally filtered by tag."),
                ("ls [--tag &lt;t&gt;] [--limit N] [--offset N]",
                                          "List file paths in library."),
                ("find &lt;keyword&gt; [--tag &lt;t&gt;] [--limit N]",
                                          "Search files by name keyword."),
                ("biggest [--tag &lt;t&gt;] [--limit N]",
                                          "Find largest files on disk."),
                ("smallest [--tag &lt;t&gt;] [--limit N]",
                                          "Find smallest files on disk."),
                ("recent [--limit N]",    "Most recently modified files."),
                ("ext [--tag &lt;t&gt;]",     "List file extension breakdown."),
                ("orphans",               "Files in DB whose path no longer exists on disk."),
                ("tagless [--limit N]",   "List files in the tagless queue."),
                ("dupes [--limit N]",     "Find possible duplicate entries (same filename, different hash)."),
            ]),
            ("TAG COMMANDS", [
                ("tag list [category] [--limit N]",              "List all tags with usage counts, optionally filtered by category."),
                ("tag search &lt;keyword&gt; [--category &lt;cat&gt;]",      "Search tags by name, optionally filtered by category."),
                ("tag add &lt;tag&gt; --file &lt;path&gt;",     "Add a tag to a specific file."),
                ("tag add &lt;tag&gt; --hash &lt;md5&gt;",      "Add a tag to a file by MD5 hash."),
                ("tag add &lt;tag&gt; --ext &lt;.ext&gt;",      "Add a tag to ALL files with a given extension. [BULK]"),
                ("tag add &lt;tag&gt; --with-tag &lt;t2&gt;",   "Add a tag to ALL files that have another tag. [BULK]"),
                ("tag remove &lt;tag&gt; --file &lt;path&gt;",  "Remove a tag from a specific file."),
                ("tag remove &lt;tag&gt; --hash &lt;md5&gt;",   "Remove a tag from a file by MD5 hash."),
                ("tag remove &lt;tag&gt; --all",                 "Remove a tag from EVERY file. [DESTRUCTIVE]"),
                ("tag rename &lt;old&gt; &lt;new&gt;",           "Rename a tag globally."),
                ("tag merge &lt;src&gt; &lt;dst&gt;",            "Merge src tag into dst, then delete src."),
                ("tag purge &lt;tag&gt;",                        "Delete a tag and all its associations. [DESTRUCTIVE]"),
                ("tag top [category] [--limit N]",               "Top N most used tags, optionally by category."),
                ("tag unused [category]",                        "Tags that are defined but used on 0 files."),
            ]),
            ("MANGA COMMANDS", [
                ("manga list",                                   "List all custom mangas."),
                ("manga info &lt;manga_id&gt;",                        "Show details, tags, and pages of a custom manga."),
                ("manga create &lt;title&gt;",                         "Create a new empty custom manga."),
                ("manga delete &lt;manga_id&gt;",                      "Delete a custom manga. [DESTRUCTIVE]"),
                ("manga rename &lt;manga_id&gt; &lt;new_title&gt;",          "Rename a custom manga."),
                ("manga tag-add &lt;manga_id&gt; &lt;tag&gt;",               "Add a tag to a custom manga."),
                ("manga tag-remove &lt;manga_id&gt; &lt;tag&gt;",            "Remove a tag from a custom manga."),
                ("manga page-add &lt;manga_id&gt; &lt;path&gt;",             "Append an image to a custom manga."),
                ("manga page-remove &lt;manga_id&gt; &lt;page_number&gt;",   "Remove a page by its page number."),
                ("manga page-attach &lt;manga_id&gt; &lt;page_number&gt;",   "Attach a page to the NEXT page (double spread)."),
                ("manga page-detach &lt;manga_id&gt; &lt;page_number&gt;",   "Detach a page from the NEXT page."),
            ]),
            ("FILE COMMANDS", [
                ("file info &lt;path&gt;",                       "Show DB record for a specific file path."),
                ("file delete --hash &lt;md5&gt;",               "Delete a file record from the DB by hash. [DESTRUCTIVE]"),
                ("file delete --tag &lt;tag&gt;",                "Delete all file records with a given tag. [DESTRUCTIVE]"),
                ("file delete --orphans",                         "Purge all DB records for missing files. [DESTRUCTIVE]"),
                ("file move --from &lt;old&gt; --to &lt;new&gt;","Update the stored path for a file in DB."),
            ]),
            ("DATABASE COMMANDS", [
                ("db optimize",     "Run PRAGMA optimize + VACUUM."),
                ("db integrity",    "Run SQLite integrity_check."),
                ("db size",         "Show database file size on disk."),
                ("db tables",       "List table names and row counts."),
                ("sql &lt;query&gt;", "Execute raw SQL. SELECT reads safely; others require Y/N confirmation."),
            ]),
            ("EXPORT", [
                ("export tags --out &lt;file.txt&gt;",            "Export all tags to a text file."),
                ("export files --tag &lt;t&gt; --out &lt;file.txt&gt;",
                                                                    "Export file paths for a tag."),
            ]),
            ("ADVANCED", [
                ("scan &lt;folder&gt; [subcommand]",                "Run maintenance scans on a folder."),
            ]),
        ]

        DETAILED = {
            "help": [
                ("help", "Show the full command list."),
                ("help &lt;command&gt;", "Show detailed usage for one command."),
                ("", "<i>Example:</i>  help tag"),
                ("", "<i>Example:</i>  help find"),
            ],
            "clear": [
                ("clear", "Clear all text from the terminal output window."),
            ],
            "version": [
                ("version", "Print the terminal version string."),
            ],
            "history": [
                ("history", "Print the last 50 commands you ran this session."),
                ("", "Use <b>UP / DOWN</b> arrow keys to navigate history in the input bar."),
                ("", "Press <b>TAB</b> to autocomplete from history."),
            ],
            "schema": [
                ("schema", "Print every table in the database with its SQL definition and column names."),
                ("", "<i>Tip:</i>  Run schema first before writing a custom sql query."),
            ],
            "stats": [
                ("stats", "Show overall counts: total files, tagless queue, total tags, avg tags/file."),
            ],
            "count": [
                ("count", "Count every file in the library."),
                ("count --tag &lt;tagname&gt;", "Count only files that have a specific tag."),
                ("", "<i>Example:</i>  count --tag \"metadata:Video\""),
            ],
            "ls": [
                ("ls", "List up to 50 file paths from the library."),
                ("ls --tag &lt;t&gt;", "Filter by tag."),
                ("ls --limit N", "Change how many results to show."),
                ("ls --offset N", "Skip the first N results (for pagination)."),
                ("", "<i>Example:</i>  ls --tag \"Artist:John\" --limit 20"),
                ("", "<i>Example:</i>  ls --limit 100 --offset 100  (page 2)"),
            ],
            "find": [
                ("find &lt;keyword&gt;", "Search file names containing the keyword."),
                ("find &lt;keyword&gt; --tag &lt;t&gt;", "Narrow search to files with a specific tag."),
                ("find &lt;keyword&gt; --limit N", "Limit results."),
                ("", "<i>Example:</i>  find \"beach\" --tag \"summer\""),
            ],
            "biggest": [
                ("biggest", "Find the 10 largest files on disk."),
                ("biggest --tag &lt;t&gt;", "Find the largest files within a specific tag."),
                ("biggest --limit N", "Change how many to show."),
                ("", "<i>Example:</i>  biggest --tag \"metadata:Video\" --limit 5"),
            ],
            "smallest": [
                ("smallest", "Find the 10 smallest files."),
                ("smallest --tag &lt;t&gt; --limit N", "Smallest within a tag."),
            ],
            "recent": [
                ("recent", "List the 20 most recently modified files on disk."),
                ("recent --limit N", "Change how many to show."),
            ],
            "ext": [
                ("ext", "Show a breakdown of all file extensions in the library with counts."),
                ("ext --tag &lt;t&gt;", "Breakdown only for files with a specific tag."),
                ("", "<i>Example:</i>  ext --tag \"metadata:Video\""),
            ],
            "orphans": [
                ("orphans", "List all DB records whose file no longer exists on disk."),
                ("", "<i>Tip:</i>  Follow up with  file delete --orphans  to clean them up."),
            ],
            "tagless": [
                ("tagless", "List files in the tagless queue (imported but not yet tagged)."),
                ("tagless --limit N", "Limit results shown."),
            ],
            "dupes": [
                ("dupes", "Find filenames that appear more than once in the library."),
                ("dupes --limit N", "Change how many duplicate groups to show."),
            ],
            "tag": [
                ("tag list [--limit N]", "List all tags alphabetically with file counts."),
                ("tag search &lt;kw&gt;", "Search tag names by keyword."),
                ("tag add &lt;tag&gt; --file &lt;path&gt;", "Add a tag to one specific file."),
                ("tag add &lt;tag&gt; --hash &lt;md5&gt;", "Add a tag to a file by its MD5 hash."),
                ("tag add &lt;tag&gt; --ext &lt;.ext&gt;", "<b>[BULK]</b> Add tag to ALL files with that extension. Prompts Y/N."),
                ("tag remove &lt;tag&gt; --file &lt;path&gt;", "Remove a tag from one file."),
                ("tag remove &lt;tag&gt; --hash &lt;md5&gt;", "Remove a tag from a file by hash."),
                ("tag remove &lt;tag&gt; --all", "<b>[DESTRUCTIVE]</b> Remove tag from every file. Prompts Y/N."),
                ("tag rename &lt;old&gt; &lt;new&gt;", "Rename a tag globally across all files."),
                ("tag merge &lt;src&gt; &lt;dst&gt;", "Move all of src files onto dst, then delete src. Prompts Y/N."),
                ("tag purge &lt;tag&gt;", "<b>[DESTRUCTIVE]</b> Delete tag and all its associations. Prompts Y/N."),
                ("tag top [--limit N]", "Top N most-used tags with a usage bar."),
                ("tag unused", "List tags that are defined but attached to 0 files."),
                ("", "<i>Example:</i>  tag add \"metadata:Video\" --ext .mp4"),
                ("", "<i>Example:</i>  tag merge \"vid\" \"metadata:Video\""),
                ("", "<i>Example:</i>  tag purge \"temp\""),
            ],
            "file": [
                ("file info &lt;path&gt;", "Show the full DB record for a file: name, hash, size, tags, etc."),
                ("file delete --hash &lt;md5&gt;", "<b>[DESTRUCTIVE]</b> Remove one file record by hash."),
                ("file delete --tag &lt;tag&gt;", "<b>[DESTRUCTIVE]</b> Remove all DB records for files with a given tag."),
                ("file delete --orphans", "<b>[DESTRUCTIVE]</b> Remove records for all files missing from disk."),
                ("file move --from &lt;old&gt; --to &lt;new&gt;", "Update a file stored path in the DB when you moved it on disk."),
                ("", "<i>Tip:</i>  In Explorer, Shift+Right-click a file → 'Copy as path', then Ctrl+V to paste."),
            ],
            "db": [
                ("db optimize", "Run PRAGMA optimize + VACUUM — shrinks size, speeds up queries."),
                ("db integrity", "Run SQLite integrity_check — reports any corruption."),
                ("db size", "Show the database file size on disk."),
                ("db tables", "List all tables with row counts."),
            ],
            "sql": [
                ("sql &lt;SELECT ...&gt;", "Run a read-only query. Results shown with column headers, up to 50 rows."),
                ("sql &lt;UPDATE/DELETE/...&gt;", "Modifying query — requires Y/N confirmation before executing."),
                ("", "<i>Tip:</i>  Run  schema  first to discover table and column names."),
                ("", "<i>Example:</i>  sql SELECT t.tag_name, COUNT(it.hash) FROM Tags t JOIN ImageTags it ON it.tag_id=t.tag_id GROUP BY t.tag_id ORDER BY 2 DESC LIMIT 10"),
                ("", "<i>Example:</i>  sql SELECT file_path FROM Images WHERE file_name LIKE '%beach%'"),
            ],
            "export": [
                ("export tags --out &lt;file.txt&gt;", "Write every tag name (one per line) to a text file."),
                ("export files --tag &lt;t&gt; --out &lt;file.txt&gt;", "Write every file path for a tag to a text file."),
                ("", "<i>Example:</i>  export files --tag \"Favorites\" --out C:/favorites.txt"),
            ],
            "scan": [
                ("scan &lt;folder&gt;", "Default (new): Find media files on disk not in the database."),
                ("scan &lt;folder&gt; new", "Find media files on disk not in the database. Fast path comparison."),
                ("scan &lt;folder&gt; new --hash", "Use MD5 hash comparison to find new files (slower, but catches renamed files)."),
                ("scan &lt;folder&gt; untagged", "Find files in the DB that have zero tags attached."),
                ("scan &lt;folder&gt; missing", "Find DB records for files that no longer exist on disk."),
                ("scan &lt;folder&gt; dupes", "Find exact byte-for-byte duplicates (by MD5) in the folder."),
                ("scan &lt;folder&gt; big", "List the largest files in the folder and show if they are in the DB."),
                ("scan &lt;folder&gt; small", "List the smallest files in the folder (useful for finding broken downloads)."),
                ("scan &lt;folder&gt; all", "Run new, untagged, and missing scans sequentially."),
                ("", "<i>Flags:</i>  --ext &lt;.mp4&gt;, --limit &lt;N&gt;, --out &lt;file.txt&gt;, --no-recurse"),
                ("", "<i>Example:</i>  scan \"D:/Library\" new --ext .mp4"),
                ("", "<i>Example:</i>  scan \"D:/Library\" dupes --out dupes.txt"),
            ],
        }

        if args:
            key = args[0].lower()
            if key in DETAILED:
                self.print_msg(f"<br><b style='color:#8957e5;'>── help: {key} ──</b>")
                for usage, desc in DETAILED[key]:
                    if not usage:
                        self.print_msg(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:#888;'>{desc}</span>")
                    else:
                        self.print_msg(
                            f"&nbsp;&nbsp;<span style='color:#00bcd4;'>{usage}</span>"
                            f"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:#888;'>{desc}</span>"
                        )
            else:
                self.print_err(f"No help found for '{key}'. Type 'help' to see all commands.")
            return

        for section_name, cmds in sections:
            self.print_msg(f"<br><b style='color:#8957e5;'>── {section_name} ──</b>")
            for usage, desc in cmds:
                self.print_msg(
                    f"&nbsp;&nbsp;<span style='color:#00bcd4;'>{usage}</span>"
                    f"<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:#888;'>{desc}</span>"
                )
        self.print_msg("<br><span style='color:#888;'>Tip: Use UP/DOWN arrows to navigate command history. TAB autocompletes.</span>")
        self.print_msg("<span style='color:#888;'>Tip: Type  help &lt;command&gt;  for detailed usage. Example:  help tag</span>")



    def cmd_version(self, _args=None):
        self.print_info("Media-Nest Power Terminal v2.0.0")
        self.print_dim("Python bindings via sqlite3 | PyQt6 UI layer")

    def cmd_history(self, _args=None):
        if not self.history:
            self.print_dim("No history yet.")
            return
        self.print_info(f"Command History ({len(self.history)} entries):")
        for i, h in enumerate(self.history[-50:], 1):
            self.print_dim(f"  [{i:>3}] {h}")

    # ═════════════════════════════════════════
    #  SCHEMA
    # ═════════════════════════════════════════
    def cmd_schema(self, _args=None):
        cur = self.db.cursor()
        cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = cur.fetchall()
        if not tables:
            self.print_warn("No tables found.")
            return
        self.print_ok(f"Schema — {len(tables)} table(s):")
        for name, sql in tables:
            self.print_info(f"<br>Table: <b>{name}</b>")
            if sql:
                self.print_dim(f"  {sql}")
            # Column summary
            cols = self.db.cursor().execute(f"PRAGMA table_info({name})").fetchall()
            col_names = [c[1] for c in cols]
            self.print_dim(f"  Columns: {', '.join(col_names)}")

    # ═════════════════════════════════════════
    #  LIBRARY INFO
    # ═════════════════════════════════════════
    def cmd_stats(self, _args=None):
        cur = self.db.cursor()
        img_count = cur.execute("SELECT COUNT(*) FROM Images").fetchone()[0]
        tag_count = cur.execute("SELECT COUNT(*) FROM Tags").fetchone()[0]
        tagless_count = cur.execute("SELECT COUNT(*) FROM tagless").fetchone()[0]
        img_tag_count = cur.execute("SELECT COUNT(*) FROM ImageTags").fetchone()[0]
        ignored_count = cur.execute("SELECT COUNT(*) FROM IgnoredPairs").fetchone()[0]
        
        manga_count = 0
        try:
            manga_count = cur.execute("SELECT COUNT(*) FROM MangaGalleries").fetchone()[0]
        except Exception:
            pass
            
        custom_manga_count = 0
        try:
            custom_manga_count = cur.execute("SELECT COUNT(*) FROM CustomMangas").fetchone()[0]
        except Exception:
            pass

        self.print_ok("Library Statistics:")
        self.print_msg(f"  &nbsp;Files (Images table)  : <b>{img_count:,}</b>")
        self.print_msg(f"  &nbsp;Manga                 : <b>{manga_count:,}</b>")
        self.print_msg(f"  &nbsp;Custom Manga          : <b>{custom_manga_count:,}</b>")
        self.print_msg(f"  &nbsp;Tagless queue         : <b>{tagless_count:,}</b>")
        self.print_msg(f"  &nbsp;Total tags defined    : <b>{tag_count:,}</b>")
        self.print_msg(f"  &nbsp;Tag-file associations : <b>{img_tag_count:,}</b>")
        self.print_msg(f"  &nbsp;Ignored dedup pairs   : <b>{ignored_count:,}</b>")

        # avg tags per file
        if img_count:
            avg = img_tag_count / img_count
            self.print_msg(f"  &nbsp;Avg tags per file      : <b>{avg:.1f}</b>")

    def cmd_count(self, args=None):
        pos, flags = _parse_flags(args or [])
        # Accept: count female  OR  count --tag female  OR  count (total)
        tag = flags.get("tag") or (pos[0] if pos else None)
        cur = self.db.cursor()
        if tag:
            # Exact match — JOIN Images ensures we only count files that still exist
            exact = cur.execute(
                "SELECT COUNT(DISTINCT i.hash) FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id WHERE t.tag_name=?", (tag,)
            ).fetchone()[0]
            if exact > 0:
                self.print_ok(f"Files tagged '{tag}': {exact:,}")
            else:
                # Fall back to partial (LIKE) match
                rows = cur.execute(
                    "SELECT t.tag_name, COUNT(DISTINCT i.hash) as cnt "
                    "FROM Images i "
                    "JOIN ImageTags it ON it.hash=i.hash "
                    "JOIN Tags t ON t.tag_id=it.tag_id "
                    "WHERE t.tag_name LIKE ? GROUP BY t.tag_id ORDER BY cnt DESC LIMIT 20",
                    (f"%{tag}%",)
                ).fetchall()
                if rows:
                    self.print_info(f"No exact tag '{tag}'. Partial matches:")
                    for name, cnt in rows:
                        self.print_msg(f"  <span style='color:#00bcd4;'>{name}</span>  {cnt:,} files")
                else:
                    self.print_warn(f"No tag found matching '{tag}'.")
        else:
            n = cur.execute("SELECT COUNT(*) FROM Images").fetchone()[0]
            self.print_ok(f"Total files in library: {n:,}")


    def cmd_ls(self, args=None):
        _, flags = _parse_flags(args or [])
        tag   = flags.get("tag")
        limit = int(flags.get("limit", 50))
        offset= int(flags.get("offset", 0))
        cur = self.db.cursor()
        if tag:
            rows = cur.execute(
                "SELECT i.file_path FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id "
                "WHERE t.tag_name=? LIMIT ? OFFSET ?", (tag, limit, offset)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT file_path FROM Images LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        if not rows:
            self.print_warn("No results.")
            return
        self.print_ok(f"Showing {len(rows)} file(s):")
        for r in rows:
            self.print_dim(f"  {r[0]}")
        self.print_dim(f"  (use --offset {offset+limit} to see next page)")

    def cmd_find(self, args=None):
        pos, flags = _parse_flags(args or [])
        if not pos:
            self.print_err("Usage: find <keyword> [--tag <t>] [--limit N]")
            return
        keyword = pos[0]
        tag = flags.get("tag")
        limit = int(flags.get("limit", 30))
        cur = self.db.cursor()
        if tag:
            rows = cur.execute(
                "SELECT i.file_path FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id "
                "WHERE t.tag_name=? AND i.file_name LIKE ? LIMIT ?",
                (tag, f"%{keyword}%", limit)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT file_path FROM Images WHERE file_name LIKE ? LIMIT ?",
                (f"%{keyword}%", limit)
            ).fetchall()
        self.print_ok(f"Found {len(rows)} result(s) for '{keyword}':")
        for r in rows:
            self.print_dim(f"  {r[0]}")

    def cmd_biggest(self, args=None):
        _, flags = _parse_flags(args or [])
        tag   = flags.get("tag")
        limit = int(flags.get("limit", 10))
        cur = self.db.cursor()
        if tag:
            rows = cur.execute(
                "SELECT i.file_path FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id "
                "WHERE t.tag_name=?", (tag,)
            ).fetchall()
        else:
            rows = cur.execute("SELECT file_path FROM Images").fetchall()

        sized = []
        for (p,) in rows:
            try:
                s = os.path.getsize(p)
                sized.append((s, p))
            except OSError:
                pass
        sized.sort(reverse=True)

        self.print_ok(f"Biggest {limit} file(s){' for tag: ' + tag if tag else ''}:")
        for size, path in sized[:limit]:
            self.print_msg(
                f"  <b>{self._fmt_bytes(size)}</b>  "
                f"<span style='color:#808080;'>{path}</span>"
            )

    def cmd_smallest(self, args=None):
        _, flags = _parse_flags(args or [])
        tag   = flags.get("tag")
        limit = int(flags.get("limit", 10))
        cur = self.db.cursor()
        if tag:
            rows = cur.execute(
                "SELECT i.file_path FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id "
                "WHERE t.tag_name=?", (tag,)
            ).fetchall()
        else:
            rows = cur.execute("SELECT file_path FROM Images").fetchall()

        sized = []
        for (p,) in rows:
            try:
                s = os.path.getsize(p)
                sized.append((s, p))
            except OSError:
                pass
        sized.sort()

        self.print_ok(f"Smallest {limit} file(s){' for tag: ' + tag if tag else ''}:")
        for size, path in sized[:limit]:
            self.print_msg(
                f"  <b>{self._fmt_bytes(size)}</b>  "
                f"<span style='color:#808080;'>{path}</span>"
            )

    def cmd_recent(self, args=None):
        _, flags = _parse_flags(args or [])
        limit = int(flags.get("limit", 20))
        cur = self.db.cursor()
        rows = cur.execute("SELECT file_path FROM Images").fetchall()
        dated = []
        for (p,) in rows:
            try:
                mtime = os.path.getmtime(p)
                dated.append((mtime, p))
            except OSError:
                pass
        dated.sort(reverse=True)
        self.print_ok(f"Most recently modified {limit} file(s):")
        import datetime
        for mtime, path in dated[:limit]:
            dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            self.print_msg(
                f"  <span style='color:#00bcd4;'>{dt}</span>"
                f"  <span style='color:#808080;'>{path}</span>"
            )

    def cmd_ext(self, args=None):
        _, flags = _parse_flags(args or [])
        tag = flags.get("tag")
        cur = self.db.cursor()
        if tag:
            rows = cur.execute(
                "SELECT i.file_name FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id "
                "WHERE t.tag_name=?", (tag,)
            ).fetchall()
        else:
            rows = cur.execute("SELECT file_name FROM Images").fetchall()

        counts: dict[str, int] = {}
        for (fname,) in rows:
            ext = os.path.splitext(fname)[1].lower() or "(none)"
            counts[ext] = counts.get(ext, 0) + 1
        if not counts:
            self.print_warn("No results.")
            return
        self.print_ok(f"Extension breakdown{' for tag: ' + tag if tag else ''}:")
        for ext, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            bar = "█" * min(cnt // max(1, max(counts.values()) // 20), 20)
            self.print_msg(f"  <span style='color:#00bcd4;'>{ext:>8}</span>  {cnt:>6,}  {bar}")

    def cmd_orphans(self, args=None):
        cur = self.db.cursor()
        rows = cur.execute("SELECT hash, file_path FROM Images").fetchall()
        orphans = [(h, p) for h, p in rows if not os.path.exists(p)]
        if not orphans:
            self.print_ok("No orphaned records found. Library is clean!")
            return
        self.print_warn(f"{len(orphans)} orphan(s) found (DB record but file missing):")
        for h, p in orphans[:50]:
            self.print_dim(f"  [{h[:8]}]  {p}")
        if len(orphans) > 50:
            self.print_dim(f"  ... and {len(orphans)-50} more. Use 'file delete --orphans' to clean up.")

    def cmd_tagless_list(self, args=None):
        _, flags = _parse_flags(args or [])
        limit = int(flags.get("limit", 30))
        cur = self.db.cursor()
        rows = cur.execute("SELECT file_path FROM tagless LIMIT ?", (limit,)).fetchall()
        total = cur.execute("SELECT COUNT(*) FROM tagless").fetchone()[0]
        self.print_ok(f"Tagless queue — {total:,} file(s) (showing {len(rows)}):")
        for r in rows:
            self.print_dim(f"  {r[0]}")

    def cmd_dupes(self, args=None):
        _, flags = _parse_flags(args or [])
        limit = int(flags.get("limit", 20))
        cur = self.db.cursor()
        rows = cur.execute(
            "SELECT file_name, COUNT(*) as cnt FROM Images "
            "GROUP BY file_name HAVING cnt > 1 "
            "ORDER BY cnt DESC LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            self.print_ok("No duplicate filenames found.")
            return
        self.print_warn(f"Files with duplicate filenames ({len(rows)} name(s)):")
        for name, cnt in rows:
            self.print_msg(
                f"  <b style='color:#ff9800;'>{cnt}x</b>"
                f"  <span style='color:#ccc;'>{name}</span>"
            )
            paths = cur.execute(
                "SELECT file_path FROM Images WHERE file_name=?", (name,)
            ).fetchall()
            for (p,) in paths:
                self.print_dim(f"       → {p}")

    # ═════════════════════════════════════════
    #  TAG COMMANDS
    # ═════════════════════════════════════════
    def cmd_tag(self, args):
        # Default to 'list' when no subcommand given, or when only flags passed (e.g. tag --limit 5)
        if not args or args[0].startswith("--"):
            self._tag_list(args or [])
            return
        sub = args[0].lower()
        rest = args[1:]
        {
            "list":        self._tag_list,
            "search":      self._tag_search,
            "smartsearch": self._tag_smartsearch,
            "add":         self._tag_add,
            "remove":      self._tag_remove,
            "rename":      self._tag_rename,
            "merge":       self._tag_merge,
            "purge":       self._tag_purge,
            "top":         self._tag_top,
            "unused":      self._tag_unused,
        }.get(sub, lambda _: self.print_err(f"Unknown tag subcommand: '{sub}'. Try: help tag"))(rest)

    def _tag_list(self, args):
        pos, flags = _parse_flags(args)
        limit = int(flags.get("limit", 50))
        category = flags.get("category") or (pos[0] if pos else None)
        cur = self.db.cursor()
        
        if category:
            rows = cur.execute(
                "SELECT t.tag_name, COUNT(it.hash) as cnt "
                "FROM Tags t LEFT JOIN ImageTags it ON it.tag_id=t.tag_id "
                "WHERE t.tag_type = ? "
                "GROUP BY t.tag_id ORDER BY t.tag_name LIMIT ?", (category, limit,)
            ).fetchall()
            self.print_ok(f"'{category}' Tags ({len(rows)} shown):")
        else:
            rows = cur.execute(
                "SELECT t.tag_name, COUNT(it.hash) as cnt "
                "FROM Tags t LEFT JOIN ImageTags it ON it.tag_id=t.tag_id "
                "GROUP BY t.tag_id ORDER BY t.tag_name LIMIT ?", (limit,)
            ).fetchall()
            self.print_ok(f"Tags ({len(rows)} shown):")
            
        for name, cnt in rows:
            self.print_msg(f"  <span style='color:#00bcd4;'>{name}</span>  ({cnt:,} files)")

    def _tag_search(self, args):
        pos, flags = _parse_flags(args)
        if not pos:
            self.print_err("Usage: tag search <keyword> [--category <cat>]")
            return
        kw = pos[0]
        category = flags.get("category")
        cur = self.db.cursor()
        
        if category:
            rows = cur.execute(
                "SELECT t.tag_name, COUNT(it.hash) "
                "FROM Tags t LEFT JOIN ImageTags it ON it.tag_id=t.tag_id "
                "WHERE t.tag_name LIKE ? AND t.tag_type = ? GROUP BY t.tag_id ORDER BY t.tag_name",
                (f"%{kw}%", category)
            ).fetchall()
            self.print_ok(f"'{category}' Tags matching '{kw}' ({len(rows)} results):")
        else:
            rows = cur.execute(
                "SELECT t.tag_name, COUNT(it.hash) "
                "FROM Tags t LEFT JOIN ImageTags it ON it.tag_id=t.tag_id "
                "WHERE t.tag_name LIKE ? GROUP BY t.tag_id ORDER BY t.tag_name",
                (f"%{kw}%",)
            ).fetchall()
            self.print_ok(f"Tags matching '{kw}' ({len(rows)} results):")
            
        for name, cnt in rows:
            self.print_msg(f"  <span style='color:#00bcd4;'>{name}</span>  ({cnt:,} files)")

    def _tag_add(self, args):
        pos, flags = _parse_flags(args)
        if not pos:
            self.print_err("Usage: tag add <tagname> [--file <path>|--hash <md5>|--ext <.ext>|--with-tag <tag>]")
            return
        tag_name = pos[0]
        cur = self.db.cursor()

        # Get or create the tag
        existing = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (tag_name,)).fetchone()
        if existing:
            tag_id = existing[0]
        else:
            cur.execute("INSERT INTO Tags(tag_name) VALUES(?)", (tag_name,))
            self.db.commit()
            tag_id = cur.lastrowid
            self.print_info(f"Created new tag: '{tag_name}' (id={tag_id})")

        if "file" in flags:
            path = flags["file"]
            rec = cur.execute("SELECT hash FROM Images WHERE file_path=?", (path,)).fetchone()
            if not rec:
                self.print_err(f"File not found in DB: {path}")
                return
            h = rec[0]
            cur.execute("INSERT OR IGNORE INTO ImageTags(hash, tag_id) VALUES(?,?)", (h, tag_id))
            self.db.commit()
            self.print_ok(f"Tag '{tag_name}' added to: {path}")

        elif "hash" in flags:
            h = flags["hash"]
            cur.execute("INSERT OR IGNORE INTO ImageTags(hash, tag_id) VALUES(?,?)", (h, tag_id))
            self.db.commit()
            self.print_ok(f"Tag '{tag_name}' added to hash {h}.")

        elif "ext" in flags:
            ext = flags["ext"].lower()
            if not ext.startswith("."):
                ext = "." + ext
            rows = cur.execute(
                "SELECT hash, file_path FROM Images WHERE LOWER(file_name) LIKE ?",
                (f"%{ext}",)
            ).fetchall()
            if not rows:
                self.print_warn(f"No files found with extension '{ext}'.")
                return
            self.print_warn(
                f"BULK: Add tag '{tag_name}' to {len(rows):,} file(s) with extension '{ext}'. [Y/N]"
            )
            self.pending_confirmation = (self._bulk_tag_add, [tag_id, tag_name, rows], {})

        elif "with-tag" in flags:
            ref_tag = flags["with-tag"]
            ref_row = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (ref_tag,)).fetchone()
            if not ref_row:
                self.print_err(f"Reference tag not found: '{ref_tag}'")
                return
            ref_id = ref_row[0]
            rows = cur.execute(
                "SELECT hash, '' FROM ImageTags WHERE tag_id=?",
                (ref_id,)
            ).fetchall()
            if not rows:
                self.print_warn(f"No files found with tag '{ref_tag}'.")
                return
            self.print_warn(
                f"BULK: Add tag '{tag_name}' to {len(rows):,} file(s) currently tagged with '{ref_tag}'. [Y/N]"
            )
            self.pending_confirmation = (self._bulk_tag_add, [tag_id, tag_name, rows], {})

        else:
            self.print_err("Specify --file <path>, --hash <md5>, --ext <.ext>, or --with-tag <tag>")

    def _bulk_tag_add(self, tag_id, tag_name, rows):
        cur = self.db.cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO ImageTags(hash, tag_id) VALUES(?,?)",
            [(h, tag_id) for h, _ in rows]
        )
        self.db.commit()
        self.print_ok(f"Tag '{tag_name}' added to {len(rows):,} file(s).")

    def _tag_remove(self, args):
        pos, flags = _parse_flags(args)
        if not pos:
            self.print_err("Usage: tag remove <tagname> [--file <p>|--hash <h>|--all]")
            return
        tag_name = pos[0]
        cur = self.db.cursor()
        tag_row = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (tag_name,)).fetchone()
        if not tag_row:
            self.print_err(f"Tag not found: '{tag_name}'")
            return
        tag_id = tag_row[0]

        if "file" in flags:
            path = flags["file"]
            rec = cur.execute("SELECT hash FROM Images WHERE file_path=?", (path,)).fetchone()
            if not rec:
                self.print_err(f"File not in DB: {path}")
                return
            cur.execute("DELETE FROM ImageTags WHERE hash=? AND tag_id=?", (rec[0], tag_id))
            self.db.commit()
            self.print_ok(f"Tag '{tag_name}' removed from: {path}")

        elif "hash" in flags:
            cur.execute("DELETE FROM ImageTags WHERE hash=? AND tag_id=?", (flags["hash"], tag_id))
            self.db.commit()
            self.print_ok(f"Tag '{tag_name}' removed from hash {flags['hash']}.")

        elif flags.get("all") is True or flags.get("all") == True:
            cnt = cur.execute("SELECT COUNT(*) FROM ImageTags WHERE tag_id=?", (tag_id,)).fetchone()[0]
            self.print_warn(
                f"DESTRUCTIVE: Remove '{tag_name}' from ALL {cnt:,} file(s). [Y/N]"
            )
            self.pending_confirmation = (self._bulk_tag_remove, [tag_id, tag_name], {})

        else:
            self.print_err("Specify --file, --hash, or --all")

    def _bulk_tag_remove(self, tag_id, tag_name):
        cur = self.db.cursor()
        cur.execute("DELETE FROM ImageTags WHERE tag_id=?", (tag_id,))
        n = cur.rowcount
        self.db.commit()
        self.print_ok(f"Removed '{tag_name}' from {n:,} file(s).")

    def _tag_rename(self, args):
        pos, _ = _parse_flags(args)
        if len(pos) < 2:
            self.print_err("Usage: tag rename <old_name> <new_name>")
            return
        old, new = pos[0], pos[1]
        cur = self.db.cursor()
        cur.execute("UPDATE Tags SET tag_name=? WHERE tag_name=?", (new, old))
        if cur.rowcount == 0:
            self.print_err(f"Tag not found: '{old}'")
            return
        self.db.commit()
        self.print_ok(f"Tag renamed: '{old}' → '{new}'")

    def _tag_merge(self, args):
        pos, _ = _parse_flags(args)
        if len(pos) < 2:
            self.print_err("Usage: tag merge <source_tag> <dest_tag>")
            return
        src, dst = pos[0], pos[1]
        cur = self.db.cursor()
        src_row = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (src,)).fetchone()
        dst_row = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (dst,)).fetchone()
        if not src_row:
            self.print_err(f"Source tag not found: '{src}'")
            return
        if not dst_row:
            self.print_err(f"Destination tag not found: '{dst}'")
            return
        src_id, dst_id = src_row[0], dst_row[0]
        cnt = cur.execute("SELECT COUNT(*) FROM ImageTags WHERE tag_id=?", (src_id,)).fetchone()[0]
        self.print_warn(
            f"Merge '{src}' ({cnt:,} files) → '{dst}', then delete '{src}'. [Y/N]"
        )
        self.pending_confirmation = (self._do_tag_merge, [src_id, dst_id, src], {})

    def _do_tag_merge(self, src_id, dst_id, src_name):
        cur = self.db.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO ImageTags(hash, tag_id) "
            "SELECT hash, ? FROM ImageTags WHERE tag_id=?", (dst_id, src_id)
        )
        cur.execute("DELETE FROM ImageTags WHERE tag_id=?", (src_id,))
        cur.execute("DELETE FROM Tags WHERE tag_id=?", (src_id,))
        self.db.commit()
        self.print_ok(f"Tag '{src_name}' merged and deleted.")

    def _tag_purge(self, args):
        pos, _ = _parse_flags(args)
        if not pos:
            self.print_err("Usage: tag purge <tag_name>")
            return
        tag_name = pos[0]
        cur = self.db.cursor()
        row = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (tag_name,)).fetchone()
        if not row:
            self.print_err(f"Tag not found: '{tag_name}'")
            return
        cnt = cur.execute("SELECT COUNT(*) FROM ImageTags WHERE tag_id=?", (row[0],)).fetchone()[0]
        self.print_warn(
            f"DESTRUCTIVE: Purge tag '{tag_name}' and remove from {cnt:,} file(s). [Y/N]"
        )
        self.pending_confirmation = (self._do_tag_purge, [row[0], tag_name], {})

    def _do_tag_purge(self, tag_id, tag_name):
        cur = self.db.cursor()
        cur.execute("DELETE FROM ImageTags WHERE tag_id=?", (tag_id,))
        cur.execute("DELETE FROM Tags WHERE tag_id=?", (tag_id,))
        self.db.commit()
        self.print_ok(f"Tag '{tag_name}' purged.")

    def _tag_top(self, args):
        pos, flags = _parse_flags(args)
        limit = int(flags.get("limit", 20))
        category = flags.get("category") or (pos[0] if pos else None)
        
        cur = self.db.cursor()
        
        if category:
            rows = cur.execute(
                "SELECT t.tag_name, COUNT(it.hash) as cnt "
                "FROM Tags t JOIN ImageTags it ON it.tag_id=t.tag_id "
                "WHERE t.tag_type = ? "
                "GROUP BY t.tag_id ORDER BY cnt DESC LIMIT ?", (category, limit,)
            ).fetchall()
            self.print_ok(f"Top {limit} '{category}' tags by usage:")
        else:
            rows = cur.execute(
                "SELECT t.tag_name, COUNT(it.hash) as cnt "
                "FROM Tags t JOIN ImageTags it ON it.tag_id=t.tag_id "
                "GROUP BY t.tag_id ORDER BY cnt DESC LIMIT ?", (limit,)
            ).fetchall()
            self.print_ok(f"Top {limit} tags by usage:")

        for i, (name, cnt) in enumerate(rows, 1):
            bar = "█" * min(cnt // max(1, rows[0][1] // 20), 20) if rows else ""
            self.print_msg(
                f"  <span style='color:#00bcd4;'>#{i:>2} {name}</span>"
                f"  <b>{cnt:,}</b>  {bar}"
            )

    def _tag_unused(self, args):
        pos, flags = _parse_flags(args)
        category = flags.get("category") or (pos[0] if pos else None)
        cur = self.db.cursor()
        
        if category:
            rows = cur.execute(
                "SELECT t.tag_name FROM Tags t "
                "LEFT JOIN ImageTags it ON it.tag_id=t.tag_id "
                "WHERE it.hash IS NULL AND t.tag_type = ? ORDER BY t.tag_name", (category,)
            ).fetchall()
            if not rows:
                self.print_ok(f"All '{category}' tags are in use!")
                return
            self.print_warn(f"{len(rows)} unused '{category}' tag(s):")
        else:
            rows = cur.execute(
                "SELECT t.tag_name FROM Tags t "
                "LEFT JOIN ImageTags it ON it.tag_id=t.tag_id "
                "WHERE it.hash IS NULL ORDER BY t.tag_name"
            ).fetchall()
            if not rows:
                self.print_ok("All tags are in use!")
                return
            self.print_warn(f"{len(rows)} unused tag(s):")
            
        for (name,) in rows:
            self.print_dim(f"  {name}")

    # ═════════════════════════════════════════
    #  FILE COMMANDS
    # ═════════════════════════════════════════
    # ═════════════════════════════════════════
    #  MANGA COMMANDS
    # ═════════════════════════════════════════
    def cmd_manga(self, args):
        if not args:
            self.print_err("Usage: manga <list|info|create|delete|rename|tag-add|tag-remove|page-add|page-remove|page-attach|page-detach>")
            return
        sub = args[0].lower()
        subargs = args[1:]

        if sub == "list":
            cur = self.db.cursor()
            custom_rows = cur.execute("SELECT manga_id, title FROM CustomMangas ORDER BY manga_id").fetchall()
            gallery_rows = cur.execute("SELECT gallery_id, title FROM MangaGalleries ORDER BY title").fetchall()
            
            if not custom_rows and not gallery_rows:
                self.print_ok("No mangas found in database.")
            else:
                if custom_rows:
                    self.print_ok(f"Custom Mangas ({len(custom_rows)}):")
                    for mid, title in custom_rows:
                        pages = cur.execute("SELECT COUNT(*) FROM CustomMangaPages WHERE manga_id=?", (mid,)).fetchone()[0]
                        self.print_msg(f"  [ID: {mid}] <span style='color:#00bcd4;'>{title}</span> ({pages} pages)")
                
                if gallery_rows:
                    self.print_ok(f"Manga Galleries ({len(gallery_rows)}):")
                    for gid, title in gallery_rows:
                        self.print_msg(f"  [ID: {gid}] <span style='color:#4caf50;'>{title}</span>")

        elif sub == "info":
            if not subargs:
                self.print_err("Usage: manga info <manga_id>")
                return
            manga_id = subargs[0]
            cur = self.db.cursor()
            row = cur.execute("SELECT title, cover_image FROM CustomMangas WHERE manga_id=?", (manga_id,)).fetchone()
            if not row:
                self.print_err(f"Manga ID {manga_id} not found.")
                return
            self.print_ok(f"Manga [{manga_id}]: {row[0]}")
            tags = cur.execute("SELECT tag_name FROM CustomMangaTags WHERE manga_id=?", (manga_id,)).fetchall()
            tag_str = ", ".join(t[0] for t in tags) if tags else "None"
            self.print_msg(f"  Tags: {tag_str}")
            pages = cur.execute("SELECT page_number, image_path, attached_to_next FROM CustomMangaPages WHERE manga_id=? ORDER BY page_number", (manga_id,)).fetchall()
            self.print_msg(f"  Pages: {len(pages)}")
            for pnum, path, attached in pages:
                att = " (Attached to next)" if attached else ""
                self.print_msg(f"    Pg {pnum}: {path}{att}")

        elif sub == "create":
            if not subargs:
                self.print_err("Usage: manga create <title>")
                return
            title = " ".join(subargs)
            cur = self.db.cursor()
            cur.execute("INSERT INTO CustomMangas (title) VALUES (?)", (title,))
            self.db.commit()
            self.print_ok(f"Created new manga [{cur.lastrowid}]: {title}")

        elif sub == "delete":
            if not subargs:
                self.print_err("Usage: manga delete <manga_id>")
                return
            manga_id = subargs[0]
            cur = self.db.cursor()
            cur.execute("DELETE FROM CustomMangas WHERE manga_id=?", (manga_id,))
            cur.execute("DELETE FROM CustomMangaPages WHERE manga_id=?", (manga_id,))
            cur.execute("DELETE FROM CustomMangaTags WHERE manga_id=?", (manga_id,))
            self.db.commit()
            self.print_ok(f"Deleted manga [{manga_id}] and all associated pages/tags.")

        elif sub == "rename":
            if len(subargs) < 2:
                self.print_err("Usage: manga rename <manga_id> <new_title>")
                return
            manga_id = subargs[0]
            title = " ".join(subargs[1:])
            cur = self.db.cursor()
            cur.execute("UPDATE CustomMangas SET title=? WHERE manga_id=?", (title, manga_id))
            self.db.commit()
            self.print_ok(f"Renamed manga [{manga_id}] to: {title}")

        elif sub == "tag-add":
            if len(subargs) < 2:
                self.print_err("Usage: manga tag-add <manga_id> <tag>")
                return
            manga_id = subargs[0]
            tag = " ".join(subargs[1:])
            cur = self.db.cursor()
            try:
                cur.execute("INSERT INTO CustomMangaTags (manga_id, tag_name) VALUES (?, ?)", (manga_id, tag))
                self.db.commit()
                self.print_ok(f"Added tag '{tag}' to manga [{manga_id}].")
            except Exception as e:
                self.print_err(f"Failed: {e}")

        elif sub == "tag-remove":
            if len(subargs) < 2:
                self.print_err("Usage: manga tag-remove <manga_id> <tag>")
                return
            manga_id = subargs[0]
            tag = " ".join(subargs[1:])
            cur = self.db.cursor()
            cur.execute("DELETE FROM CustomMangaTags WHERE manga_id=? AND tag_name=?", (manga_id, tag))
            self.db.commit()
            self.print_ok(f"Removed tag '{tag}' from manga [{manga_id}].")

        elif sub == "page-add":
            if len(subargs) < 2:
                self.print_err("Usage: manga page-add <manga_id> <file_path>")
                return
            manga_id = subargs[0]
            path = " ".join(subargs[1:])
            cur = self.db.cursor()
            cnt = cur.execute("SELECT COUNT(*) FROM CustomMangaPages WHERE manga_id=?", (manga_id,)).fetchone()[0]
            cur.execute("INSERT INTO CustomMangaPages (manga_id, image_path, page_number) VALUES (?, ?, ?)", (manga_id, path, cnt + 1))
            self.db.commit()
            self.print_ok(f"Appended page {cnt+1} to manga [{manga_id}].")

        elif sub == "page-remove":
            if len(subargs) < 2:
                self.print_err("Usage: manga page-remove <manga_id> <page_number>")
                return
            manga_id = subargs[0]
            pnum = int(subargs[1])
            cur = self.db.cursor()
            cur.execute("DELETE FROM CustomMangaPages WHERE manga_id=? AND page_number=?", (manga_id, pnum))
            cur.execute("UPDATE CustomMangaPages SET page_number = page_number - 1 WHERE manga_id=? AND page_number > ?", (manga_id, pnum))
            self.db.commit()
            self.print_ok(f"Removed page {pnum} from manga [{manga_id}]. Subsequent pages shifted.")

        elif sub == "page-attach":
            if len(subargs) < 2:
                self.print_err("Usage: manga page-attach <manga_id> <page_number>")
                return
            manga_id = subargs[0]
            pnum = int(subargs[1])
            cur = self.db.cursor()
            cur.execute("UPDATE CustomMangaPages SET attached_to_next=1 WHERE manga_id=? AND page_number=?", (manga_id, pnum))
            self.db.commit()
            self.print_ok(f"Attached page {pnum} to next page in manga [{manga_id}].")

        elif sub == "page-detach":
            if len(subargs) < 2:
                self.print_err("Usage: manga page-detach <manga_id> <page_number>")
                return
            manga_id = subargs[0]
            pnum = int(subargs[1])
            cur = self.db.cursor()
            cur.execute("UPDATE CustomMangaPages SET attached_to_next=0 WHERE manga_id=? AND page_number=?", (manga_id, pnum))
            self.db.commit()
            self.print_ok(f"Detached page {pnum} from next page in manga [{manga_id}].")

        else:
            self.print_err(f"Unknown manga subcommand: '{sub}'")

    def cmd_file(self, args):
        if not args:
            self.print_err("Usage: file <subcommand>. Type 'help' for details.")
            return
        sub = args[0].lower()
        rest = args[1:]
        {
            "info":   self._file_info,
            "delete": self._file_delete,
            "move":   self._file_move,
        }.get(sub, lambda _: self.print_err(f"Unknown file subcommand: '{sub}'"))(rest)

    def _file_info(self, args):
        pos, _ = _parse_flags(args)
        if not pos:
            self.print_err("Usage: file info <path>")
            return
        path = pos[0]
        cur = self.db.cursor()
        rec = cur.execute(
            "SELECT hash, file_path, file_name FROM Images WHERE file_path=?", (path,)
        ).fetchone()
        if not rec:
            self.print_warn(f"No record found for: {path}")
            return
        h, fp, fn = rec
        self.print_ok(f"File record:")
        self.print_msg(f"  Name  : {fn}")
        self.print_msg(f"  Path  : {fp}")
        self.print_msg(f"  Hash  : {h}")
        # Disk info
        if os.path.exists(fp):
            import datetime
            size  = os.path.getsize(fp)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
            self.print_msg(f"  Size  : {self._fmt_bytes(size)}")
            self.print_msg(f"  Mtime : {mtime}")
        else:
            self.print_warn("  [File not found on disk]")
        # Tags
        tags = cur.execute(
            "SELECT t.tag_name FROM Tags t "
            "JOIN ImageTags it ON it.tag_id=t.tag_id "
            "WHERE it.hash=? ORDER BY t.tag_name", (h,)
        ).fetchall()
        tag_str = ", ".join(t[0] for t in tags) if tags else "(none)"
        self.print_msg(f"  Tags  : {tag_str}")

    def _file_delete(self, args):
        _, flags = _parse_flags(args)
        cur = self.db.cursor()

        if "hash" in flags:
            h = flags["hash"]
            rec = cur.execute("SELECT file_path FROM Images WHERE hash=?", (h,)).fetchone()
            if not rec:
                self.print_err(f"No record with hash: {h}")
                return
            self.print_warn(f"Delete DB record for hash '{h}' ({rec[0]})? [Y/N]")
            self.pending_confirmation = (self._do_delete_hash, [h], {})

        elif "tag" in flags:
            tag = flags["tag"]
            tag_row = cur.execute("SELECT tag_id FROM Tags WHERE tag_name=?", (tag,)).fetchone()
            if not tag_row:
                self.print_err(f"Tag not found: '{tag}'")
                return
            cnt = cur.execute(
                "SELECT COUNT(*) FROM ImageTags WHERE tag_id=?", (tag_row[0],)
            ).fetchone()[0]
            self.print_warn(
                f"DESTRUCTIVE: Delete {cnt:,} DB record(s) tagged '{tag}'. [Y/N]"
            )
            self.pending_confirmation = (self._do_delete_by_tag, [tag_row[0], tag], {})

        elif flags.get("orphans") is True:
            rows = cur.execute("SELECT hash, file_path FROM Images").fetchall()
            orphans = [(h, p) for h, p in rows if not os.path.exists(p)]
            if not orphans:
                self.print_ok("No orphans to remove.")
                return
            self.print_warn(
                f"Purge {len(orphans):,} orphaned DB record(s) (files missing from disk)? [Y/N]"
            )
            self.pending_confirmation = (self._do_delete_orphans, [orphans], {})

        else:
            self.print_err("Usage: file delete --hash <md5> | --tag <t> | --orphans")

    def _do_delete_hash(self, h):
        cur = self.db.cursor()
        cur.execute("DELETE FROM ImageTags WHERE hash=?", (h,))
        cur.execute("DELETE FROM Images WHERE hash=?", (h,))
        self.db.commit()
        self.print_ok(f"Deleted record for hash {h}.")

    def _do_delete_by_tag(self, tag_id, tag_name):
        cur = self.db.cursor()
        hashes = [r[0] for r in cur.execute(
            "SELECT hash FROM ImageTags WHERE tag_id=?", (tag_id,)
        ).fetchall()]
        cur.execute("DELETE FROM ImageTags WHERE hash IN ({})".format(
            ",".join("?" * len(hashes))), hashes)
        cur.execute("DELETE FROM Images WHERE hash IN ({})".format(
            ",".join("?" * len(hashes))), hashes)
        self.db.commit()
        self.print_ok(f"Deleted {len(hashes):,} record(s) tagged '{tag_name}'.")

    def _do_delete_orphans(self, orphans):
        cur = self.db.cursor()
        for h, _ in orphans:
            cur.execute("DELETE FROM ImageTags WHERE hash=?", (h,))
            cur.execute("DELETE FROM Images WHERE hash=?", (h,))
        self.db.commit()
        self.print_ok(f"Removed {len(orphans):,} orphaned record(s).")

    def _file_move(self, args):
        _, flags = _parse_flags(args)
        old = flags.get("from")
        new = flags.get("to")
        if not old or not new:
            self.print_err("Usage: file move --from <old_path> --to <new_path>")
            return
        cur = self.db.cursor()
        rec = cur.execute("SELECT hash FROM Images WHERE file_path=?", (old,)).fetchone()
        if not rec:
            self.print_err(f"No record for path: {old}")
            return
        new_name = os.path.basename(new)
        cur.execute(
            "UPDATE Images SET file_path=?, file_name=? WHERE file_path=?",
            (new, new_name, old)
        )
        self.db.commit()
        self.print_ok(f"Updated path: '{old}' → '{new}'")

    # ═════════════════════════════════════════
    #  DB COMMANDS
    # ═════════════════════════════════════════
    def cmd_db(self, args):
        if not args:
            self.print_err("Usage: db [optimize|integrity|size|tables]")
            return
        sub = args[0].lower()

        if sub == "optimize":
            self.print_info("Running PRAGMA optimize + VACUUM...")
            QApplication.processEvents()
            try:
                self.db.execute("PRAGMA optimize")
                self.db.execute("VACUUM")
                self.print_ok("Database optimization complete.")
            except Exception as e:
                self.print_err(f"Failed: {e}")

        elif sub == "integrity":
            self.print_info("Running integrity_check...")
            try:
                res = self.db.execute("PRAGMA integrity_check").fetchall()
                if res and res[0][0] == "ok":
                    self.print_ok("Database integrity: OK")
                else:
                    for r in res:
                        self.print_warn(str(r[0]))
            except Exception as e:
                self.print_err(str(e))

        elif sub == "size":
            cur = self.db.cursor()
            path = cur.execute("PRAGMA database_list").fetchone()
            if path and path[2]:
                try:
                    sz = os.path.getsize(path[2])
                    self.print_ok(f"Database file size: {self._fmt_bytes(sz)}")
                    self.print_dim(f"Path: {path[2]}")
                except OSError:
                    self.print_warn("Could not determine size.")
            else:
                self.print_warn("No file path available (in-memory DB?).")

        elif sub == "tables":
            cur = self.db.cursor()
            tables = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            self.print_ok(f"{len(tables)} table(s):")
            for (name,) in tables:
                cnt = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                self.print_msg(
                    f"  <span style='color:#00bcd4;'>{name:<30}</span>  {cnt:,} rows"
                )
        else:
            self.print_err(f"Unknown db subcommand: '{sub}'")

    # ═════════════════════════════════════════
    #  RAW SQL
    # ═════════════════════════════════════════
    def cmd_sql(self, raw_args):
        query = (raw_args if isinstance(raw_args, str) else " ".join(raw_args)).strip()
        if not query:
            self.print_err("Usage: sql <query>")
            return
        first = query.split()[0].lower()
        if first in ("select", "pragma", "explain"):
            try:
                cur = self.db.cursor()
                cur.execute(query)
                rows = cur.fetchall()
                desc = cur.description or []
                col_names = [d[0] for d in desc]
                if col_names:
                    self.print_info("  " + "  |  ".join(col_names))
                    self.print_dim("  " + "-" * (sum(len(c)+5 for c in col_names)))
                if not rows:
                    self.print_msg("Query returned 0 rows.")
                else:
                    for row in rows[:50]:
                        self.print_msg("  " + "  |  ".join(str(v) for v in row))
                    if len(rows) > 50:
                        self.print_dim(f"  ... {len(rows)-50} more rows not shown.")
                self.print_ok(f"Returned {len(rows)} row(s).")
            except Exception as e:
                self.print_err(f"SQL Error: {e}")
        else:
            self.print_warn(f"DANGEROUS QUERY: {query}")
            self.print_warn("This modifies the database. Confirm? [Y/N]")
            self.pending_confirmation = (self._exec_destructive_sql, [query], {})

    def _exec_destructive_sql(self, query):
        try:
            cur = self.db.cursor()
            cur.execute(query)
            self.db.commit()
            self.print_ok(f"Executed. Rows affected: {cur.rowcount}")
        except Exception as e:
            self.print_err(f"SQL Error: {e}")

    # ═════════════════════════════════════════
    #  EXPORT
    # ═════════════════════════════════════════
    def cmd_export(self, args):
        _, flags = _parse_flags(args or [])
        tag = flags.get("tag")
        out = flags.get("out")

        # Determine what to export
        if not args:
            self.print_err("Usage: export tags --out <file> | export files --tag <t> --out <file>")
            return

        sub = args[0].lower()
        cur = self.db.cursor()

        if sub == "tags":
            rows = cur.execute("SELECT tag_name FROM Tags ORDER BY tag_name").fetchall()
            lines = [r[0] for r in rows]
            target = out or "exported_tags.txt"
            try:
                with open(target, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.print_ok(f"Exported {len(lines):,} tags → {os.path.abspath(target)}")
            except IOError as e:
                self.print_err(str(e))

        elif sub == "files":
            if not tag:
                self.print_err("Usage: export files --tag <t> --out <file>")
                return
            rows = cur.execute(
                "SELECT i.file_path FROM Images i "
                "JOIN ImageTags it ON it.hash=i.hash "
                "JOIN Tags t ON t.tag_id=it.tag_id "
                "WHERE t.tag_name=?", (tag,)
            ).fetchall()
            target = out or f"exported_{tag.replace(' ','_')}.txt"
            try:
                with open(target, "w", encoding="utf-8") as f:
                    f.write("\n".join(r[0] for r in rows))
                self.print_ok(f"Exported {len(rows):,} paths → {os.path.abspath(target)}")
            except IOError as e:
                self.print_err(str(e))
        else:
            self.print_err(f"Unknown export type: '{sub}'")

    # ═════════════════════════════════════════
    #  Utilities
    # ═════════════════════════════════════════
    @staticmethod
    def _fmt_bytes(n):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"

    # ═════════════════════════════════════════
    #  SCAN COMMAND
    # ═════════════════════════════════════════
    # Supported media extensions (same set the importer recognises)
    _MEDIA_EXTS = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
        ".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v",
        ".mp3", ".ogg", ".flac", ".wav", ".aac",
        ".pdf", ".cbz", ".cbr",
    }

    def cmd_scan(self, args):
        """
        scan <folder> [subcommand] [options]

        Subcommands (default: new):
          new       Files on disk NOT in library.db at all
          untagged  Files in library.db that have zero tags
          missing   DB records whose file no longer exists on disk
          dupes     Files with identical MD5 (exact content duplicates)
          big       Largest files in the folder
          small     Smallest files in the folder
          all       Run new + untagged + missing in one pass

        Flags:
          --ext <.mp4>   Only consider files with this extension
          --limit N      Cap result rows (default 50)
          --hash         For 'new': also compute MD5 to check by content (slow)
          --out <file>   Write results to a text file
          --recurse / --no-recurse   (default: recurse into subfolders)
        """
        if not args:
            self.print_err(
                "Usage: scan &lt;folder&gt; [new|untagged|missing|dupes|big|small|all] [--ext .mp4] [--limit N] [--hash] [--out file]"
            )
            return

        pos, flags = _parse_flags(args)

        # First positional = folder, second optional = subcommand
        folder    = pos[0] if pos else None
        subcmd    = (pos[1].lower() if len(pos) > 1 else "new")
        ext_filter= flags.get("ext", "").lower()
        limit     = int(flags.get("limit", 50))
        use_hash  = "hash" in flags
        out_file  = flags.get("out")
        no_recurse= "no-recurse" in flags

        if not folder:
            self.print_err("Please specify a folder to scan.")
            return

        folder = folder.rstrip("/\\")
        if not os.path.isdir(folder):
            self.print_err(f"Folder not found: {folder}")
            return

        self.print_info(f"Scanning: {folder}")
        self.print_dim(f"Mode: {subcmd}  |  ext: {ext_filter or 'all media'}  |  limit: {limit}  |  hash: {use_hash}")
        QApplication.processEvents()

        if subcmd == "all":
            self._scan_new(folder, ext_filter, limit, use_hash, out_file, no_recurse)
            self._scan_untagged(folder, ext_filter, limit, out_file)
            self._scan_missing(limit, out_file)
            return

        dispatch = {
            "new":      lambda: self._scan_new(folder, ext_filter, limit, use_hash, out_file, no_recurse),
            "untagged": lambda: self._scan_untagged(folder, ext_filter, limit, out_file),
            "missing":  lambda: self._scan_missing(limit, out_file),
            "dupes":    lambda: self._scan_dupes(folder, ext_filter, limit, out_file, no_recurse),
            "big":      lambda: self._scan_size(folder, ext_filter, limit, out_file, no_recurse, biggest=True),
            "small":    lambda: self._scan_size(folder, ext_filter, limit, out_file, no_recurse, biggest=False),
        }
        fn = dispatch.get(subcmd)
        if fn:
            fn()
        else:
            self.print_err(f"Unknown scan subcommand '{subcmd}'. Try: new, untagged, missing, dupes, big, small, all")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _iter_files(self, folder, ext_filter, no_recurse):
        """Walk folder and yield absolute file paths matching the ext filter."""
        yields = 0
        if no_recurse:
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath):
                    if self._ext_ok(fpath, ext_filter):
                        yield fpath
                        yields += 1
                        if yields % 100 == 0: QApplication.processEvents()
        else:
            for root, _dirs, files in os.walk(folder):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if self._ext_ok(fpath, ext_filter):
                        yield fpath
                        yields += 1
                        if yields % 100 == 0: QApplication.processEvents()

    def _ext_ok(self, path, ext_filter):
        ext = os.path.splitext(path)[1].lower()
        if ext_filter:
            return ext == ext_filter
        return ext in self._MEDIA_EXTS

    @staticmethod
    def _md5(path):
        import hashlib
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return None

    def _write_out(self, lines, out_file):
        if out_file and lines:
            try:
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.print_ok(f"Results written to: {os.path.abspath(out_file)}")
            except IOError as e:
                self.print_err(f"Could not write output file: {e}")

    # ── scan new ─────────────────────────────────────────────────────────────
    def _scan_new(self, folder, ext_filter, limit, use_hash, out_file, no_recurse):
        self.print_msg("<br><b style='color:#8957e5;'>-- SCAN: NEW (not in library) --</b>")
        QApplication.processEvents()

        cur = self.db.cursor()

        if use_hash:
            # Hash-based: slower but catches renamed files
            known_hashes = set(r[0] for r in cur.execute("SELECT hash FROM Images").fetchall())
            new_files, checked = [], 0
            for fpath in self._iter_files(folder, ext_filter, no_recurse):
                checked += 1
                if checked % 200 == 0:
                    self.print_dim(f"  Hashing {checked} files...")
                    QApplication.processEvents()
                h = self._md5(fpath)
                if h and h not in known_hashes:
                    new_files.append(fpath)
            self.print_ok(f"Scanned {checked:,} files. {len(new_files):,} not in library (by MD5):")
        else:
            # Path-based: fast, catches files the DB doesn't know about by path
            known_paths = set(r[0] for r in cur.execute("SELECT file_path FROM Images").fetchall())
            # Also check tagless queue
            known_paths.update(r[0] for r in cur.execute("SELECT file_path FROM tagless").fetchall())
            
            # Pre-normalize to O(1) lookups
            normalized_known = {os.path.normpath(p) for p in known_paths if p}
            
            new_files, checked = [], 0
            for fpath in self._iter_files(folder, ext_filter, no_recurse):
                checked += 1
                if checked % 500 == 0:
                    self.print_dim(f"  Checked {checked:,} paths...")
                    QApplication.processEvents()
                
                if os.path.normpath(fpath) not in normalized_known:
                    new_files.append(fpath)
            self.print_ok(f"Scanned {checked:,} files. {len(new_files):,} not in library (by path):")
            if not use_hash:
                self.print_dim("  (Tip: add --hash to also detect renamed files)")

        out_lines = new_files
        for path in new_files[:limit]:
            try:
                size = self._fmt_bytes(os.path.getsize(path))
            except OSError:
                size = "?"
            self.print_msg(f"  <span style='color:#ff9800;'>[NEW]</span> <span style='color:#ccc;'>{path}</span>  <span style='color:#808080;'>({size})</span>")
        if len(new_files) > limit:
            msg = f"  ... and {len(new_files)-limit:,} more."
            msg += " Check output file." if out_file else " Use --limit N or --out file.txt to see all."
            self.print_dim(msg)
        self._write_out(out_lines, out_file)

    # ── scan untagged ────────────────────────────────────────────────────────
    def _scan_untagged(self, folder, ext_filter, limit, out_file):
        self.print_msg("<br><b style='color:#8957e5;'>-- SCAN: UNTAGGED (in library, no tags) --</b>")
        QApplication.processEvents()

        cur = self.db.cursor()
        folder_norm = os.path.normpath(folder)

        rows = cur.execute(
            "SELECT i.file_path FROM Images i "
            "LEFT JOIN ImageTags it ON it.hash=i.hash "
            "WHERE it.hash IS NULL"
        ).fetchall()

        # Filter to the scanned folder
        filtered = []
        for (p,) in rows:
            if ext_filter and not p.lower().endswith(ext_filter):
                continue
            if os.path.normpath(p).startswith(folder_norm):
                filtered.append(p)

        self.print_ok(f"{len(filtered):,} untagged file(s) inside '{folder}':")
        out_lines = filtered
        for path in filtered[:limit]:
            exists = "OK" if os.path.exists(path) else "MISSING"
            color  = "#cccccc" if exists == "OK" else "#f44336"
            self.print_msg(f"  <span style='color:{color};'>[{exists}]</span> <span style='color:#808080;'>{path}</span>")
        if len(filtered) > limit:
            msg = f"  ... and {len(filtered)-limit:,} more."
            msg += " Check output file." if out_file else " Use --limit N or --out file.txt to see all."
            self.print_dim(msg)
        self._write_out(out_lines, out_file)

    # ── scan missing ─────────────────────────────────────────────────────────
    def _scan_missing(self, limit, out_file):
        self.print_msg("<br><b style='color:#8957e5;'>-- SCAN: MISSING (DB records with no file on disk) --</b>")
        QApplication.processEvents()

        cur = self.db.cursor()
        rows = cur.execute("SELECT hash, file_path FROM Images").fetchall()
        missing = [(h, p) for h, p in rows if not os.path.exists(p)]

        self.print_ok(f"{len(missing):,} orphaned record(s) (file gone from disk):")
        out_lines = [path for _, path in missing]
        for h, path in missing[:limit]:
            self.print_msg(
                f"  <span style='color:#f44336;'>[GONE]</span>"
                f"  <span style='color:#808080;'>[{h[:8]}]</span>"
                f"  <span style='color:#ccc;'>{path}</span>"
            )
        if len(missing) > limit:
            msg = f"  ... and {len(missing)-limit:,} more."
            msg += " Check output file." if out_file else " Use --limit N or --out file.txt to see all."
            self.print_dim(msg)
        if missing:
            self.print_dim("  Tip: run  file delete --orphans  to purge these records.")
        self._write_out(out_lines, out_file)

    # ── scan dupes ───────────────────────────────────────────────────────────
    def _scan_dupes(self, folder, ext_filter, limit, out_file, no_recurse):
        self.print_msg("<br><b style='color:#8957e5;'>-- SCAN: CONTENT DUPES (same MD5) --</b>")
        self.print_dim("  Computing MD5 hashes... (this may take a moment for large folders)")
        QApplication.processEvents()

        from collections import defaultdict
        hash_map = defaultdict(list)
        checked  = 0
        for fpath in self._iter_files(folder, ext_filter, no_recurse):
            h = self._md5(fpath)
            if h:
                hash_map[h].append(fpath)
            checked += 1
            if checked % 200 == 0:
                self.print_dim(f"  Hashed {checked:,} files...")
                QApplication.processEvents()

        dupe_groups = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
        self.print_ok(f"Scanned {checked:,} files. Found {len(dupe_groups):,} duplicate group(s):")

        out_lines = [p for paths in dupe_groups.values() for p in paths]
        for i, (h, paths) in enumerate(list(dupe_groups.items())[:limit]):
            try:
                size = self._fmt_bytes(os.path.getsize(paths[0]))
            except OSError:
                size = "?"
            self.print_msg(
                f"  <b style='color:#ff9800;'>Group {i+1}</b>  "
                f"MD5: <span style='color:#808080;'>{h[:12]}...</span>  "
                f"<span style='color:#ccc;'>({size} each, {len(paths)} copies)</span>"
            )
            for path in paths:
                self.print_dim(f"       {path}")
        if len(dupe_groups) > limit:
            msg = f"  ... and {len(dupe_groups)-limit:,} more groups."
            msg += " Check output file." if out_file else " Use --limit N or --out file.txt to see all."
            self.print_dim(msg)
        self._write_out(out_lines, out_file)

    # ── scan big / small ─────────────────────────────────────────────────────
    def _scan_size(self, folder, ext_filter, limit, out_file, no_recurse, biggest=True):
        label = "BIG" if biggest else "SMALL"
        self.print_msg(f"<br><b style='color:#8957e5;'>-- SCAN: {label} --</b>")
        QApplication.processEvents()

        sized = []
        for fpath in self._iter_files(folder, ext_filter, no_recurse):
            try:
                sized.append((os.path.getsize(fpath), fpath))
            except OSError:
                pass
        sized.sort(reverse=biggest)

        total_size = sum(s for s, _ in sized)
        self.print_ok(
            f"{len(sized):,} files in '{folder}'  |  "
            f"Total: {self._fmt_bytes(total_size)}  |  "
            f"Showing {'largest' if biggest else 'smallest'} {min(limit, len(sized))}:"
        )
        out_lines = [f"{self._fmt_bytes(s)}  {p}" for s, p in sized]
        for size, path in sized[:limit]:
            in_db = "DB" if self.db.execute(
                "SELECT 1 FROM Images WHERE file_path=? LIMIT 1",
                (os.path.normpath(path),)
            ).fetchone() else "NEW"
            db_color = "#4caf50" if in_db == "DB" else "#ff9800"
            self.print_msg(
                f"  <b>{self._fmt_bytes(size)}</b>"
                f"  <span style='color:{db_color};'>[{in_db}]</span>"
                f"  <span style='color:#808080;'>{path}</span>"
            )
        self._write_out(out_lines, out_file)

