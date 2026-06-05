import sys
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy, QWidget, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import (
    QPixmap, QDesktopServices, QColor, QPainter,
    QLinearGradient, QBrush, QPen, QFont
)

from Src.Logic.paths import resource_path


# ─────────────────────────────────────────────────────────
#  Colour tokens
# ─────────────────────────────────────────────────────────
BG_DARK      = "#161618"
BG_CARD      = "#1E1E22"
BG_CARD_HVR  = "#27272D"
BORDER       = "#2D2D35"
BORDER_HVR   = "#4A4A5A"
TEXT_WHITE   = "#F0F0F5"
TEXT_MUTED   = "#7A7A90"
ACCENT_PINK  = "#FF4D6D"
ACCENT_BLU   = "#4D9FFF"


class GradientBanner(QWidget):
    """Gradient hero banner painted with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        grad = QLinearGradient(0, 0, r.width(), r.height())
        grad.setColorAt(0.0,  QColor("#14082A"))
        grad.setColorAt(0.5,  QColor("#2A0E40"))
        grad.setColorAt(1.0,  QColor("#3A0D1E"))
        p.fillRect(r, QBrush(grad))

        # top-right glow
        c1 = QColor(255, 77, 109, 45)
        p.setBrush(QBrush(c1))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(r.width() - 100, -50, 200, 200)

        # bottom-left glow
        c2 = QColor(77, 159, 255, 30)
        p.setBrush(QBrush(c2))
        p.drawEllipse(-70, r.height() - 70, 180, 180)

        # bottom divider
        pen = QPen(QColor(255, 77, 109, 70))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.drawLine(0, r.height() - 1, r.width(), r.height() - 1)

        p.end()


class GridCard(QPushButton):
    """
    Square-ish card for the 3-column grid.
    Shows icon (top), bold title, subtitle, and an accent bottom border.
    """

    def __init__(self, icon_path, title, subtitle, url,
                 accent="#4D9FFF", icon_size=44, parent=None):
        super().__init__(parent)
        self._url   = url
        self._accent = accent

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(120)

        self._base_ss = f"""
            QPushButton {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 14px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {BG_CARD_HVR};
                border: 1px solid {accent};
            }}
            QPushButton:pressed {{
                background-color: {BG_CARD};
            }}
        """
        self.setStyleSheet(self._base_ss)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)

        # Layout
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 16, 12, 12)
        col.setSpacing(6)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Icon
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(icon_size, icon_size)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        px = QPixmap(icon_path)
        if not px.isNull():
            icon_lbl.setPixmap(
                px.scaled(QSize(icon_size, icon_size),
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        icon_wrap = QHBoxLayout()
        icon_wrap.addStretch()
        icon_wrap.addWidget(icon_lbl)
        icon_wrap.addStretch()
        col.addLayout(icon_wrap)

        # Title
        t_lbl = QLabel(title)
        tf = QFont()
        tf.setPointSize(10)
        tf.setBold(True)
        t_lbl.setFont(tf)
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; background: transparent; border: none;")
        t_lbl.setWordWrap(True)
        col.addWidget(t_lbl)

        # Subtitle
        s_lbl = QLabel(subtitle)
        sf = QFont()
        sf.setPointSize(8)
        s_lbl.setFont(sf)
        s_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent; border: none;")
        s_lbl.setWordWrap(True)
        col.addWidget(s_lbl)

        col.addStretch()

        # Accent bottom pill
        pill = QLabel()
        pill.setFixedHeight(3)
        pill.setStyleSheet(
            f"background-color: {accent}; border-radius: 2px;"
        )
        col.addWidget(pill)

        self.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._url)))


class SectionLabel(QLabel):
    """ALL-CAPS pill section label with left accent bar."""
    def __init__(self, text, accent="#4D9FFF", parent=None):
        super().__init__(text.upper(), parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setFixedHeight(26)
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        self.setFont(f)
        self.setStyleSheet(f"""
            QLabel {{
                color: {accent};
                background: transparent;
                padding-left: 8px;
                border-left: 3px solid {accent};
                letter-spacing: 2px;
            }}
        """)


class SupportDialog(QDialog):
    """
    Premium Support & Community dialog — 3 × 2 card grid layout.
    Row 1: Ko-fi | Buy Me a Coffee | Patreon   (donate)
    Row 2: GitHub | Discord | Instagram         (community)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("Support & Community")
        self.setMinimumWidth(580)
        self.setMinimumHeight(480)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Hero Banner ────────────────────────────────────────
        banner = GradientBanner(self)
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(26, 18, 26, 14)
        bl.setSpacing(4)

        hl = QLabel("❤️  Support Media Nest")
        hf = QFont()
        hf.setPointSize(16)
        hf.setBold(True)
        hl.setFont(hf)
        hl.setStyleSheet(f"color: {TEXT_WHITE}; background: transparent;")
        bl.addWidget(hl)

        sl = QLabel(
            "If you enjoy the app, consider supporting its development — "
            "every bit helps keep the project alive and growing!"
        )
        sl.setWordWrap(True)
        sf = QFont()
        sf.setPointSize(9)
        sl.setFont(sf)
        sl.setStyleSheet("color: rgba(240,240,245,0.60); background: transparent;")
        bl.addWidget(sl)

        root.addWidget(banner)

        # ── Body ──────────────────────────────────────────────
        body_w = QWidget()
        body_w.setStyleSheet(f"background-color: {BG_DARK};")
        body = QVBoxLayout(body_w)
        body.setContentsMargins(22, 18, 22, 18)
        body.setSpacing(10)

        # ── Row 1: Donate ─────────────────────────────────────
        body.addWidget(SectionLabel("Contribute Financially", accent=ACCENT_PINK))
        body.addSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(GridCard(
            get_asset_path("Ko-fi.png"),
            "Ko-fi", "One-time tip ☕",
            "https://ko-fi.com/yuvi427183",
            accent="#5BC0EB", icon_size=44
        ))
        row1.addWidget(GridCard(
            get_asset_path("buymeacoffee.png"),
            "Buy Me a Coffee", "Quick donation",
            "https://buymeacoffee.com/yuvi9587",
            accent="#FFDD57", icon_size=44
        ))
        row1.addWidget(GridCard(
            get_asset_path("patreon.png"),
            "Patreon", "Monthly support",
            "https://www.patreon.com/Yuvi102",
            accent="#FF424D", icon_size=44
        ))
        body.addLayout(row1)

        # ── Divider ───────────────────────────────────────────
        body.addSpacing(14)
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {BORDER}; border: none;")
        body.addWidget(div)
        body.addSpacing(10)

        # ── Row 2: Community ──────────────────────────────────
        body.addWidget(SectionLabel("Get Help & Connect", accent=ACCENT_BLU))
        body.addSpacing(6)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(GridCard(
            get_asset_path("github.png"),
            "GitHub", "Report issues",
            "https://github.com/Yuvi9587/Media-Nest",
            accent="#E6EDF3", icon_size=38
        ))
        row2.addWidget(GridCard(
            get_asset_path("discord.png"),
            "Discord", "Join the server",
            "https://discord.gg/BqP64XTdJN",
            accent="#5865F2", icon_size=38
        ))
        row2.addWidget(GridCard(
            get_asset_path("instagram.png"),
            "Instagram", "Follow me",
            "https://www.instagram.com/uvi.arts/",
            accent="#C13584", icon_size=38
        ))
        body.addLayout(row2)

        # ── Close button ──────────────────────────────────────
        body.addSpacing(18)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(38)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_CARD};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {BG_CARD_HVR};
                color: {TEXT_WHITE};
                border-color: {BORDER_HVR};
            }}
        """)
        body.addWidget(close_btn)

        root.addWidget(body_w)


def get_asset_path(filename):
    return resource_path(os.path.join("assets", filename))
