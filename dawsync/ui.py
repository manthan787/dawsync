"""Desktop presentation, kept separate from the sync engine."""
from PySide6.QtCore import Qt, QSize, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLayout, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTextEdit, QVBoxLayout, QWidget)


THEME = """
QMainWindow, QWidget#workspace { background: #0d1018; }
QWidget#content, QScrollArea { background: #0d1018; border: none; }
QWidget { color: #edf0f7; font-family: 'SF Pro Text', 'Helvetica Neue'; font-size: 13px; }
QFrame#sidebar { background: #11151f; border-right: 1px solid #252c3b; }
QScrollArea#projectList, QWidget#projectItems { background: #11151f; border: none; }
QPushButton#project { background: transparent; border: none; color: #a5b0c5;
    text-align: left; padding: 10px 14px; border-radius: 9px; font-weight: 500; }
QPushButton#project:hover { background: #1d2433; color: #e1e7f2; }
QPushButton#project:checked { background: #2c2542; color: #d8caff; }
QPushButton#project:focus { border: 1px solid #776395; }
QPushButton#project:disabled { color: #68748a; }
QFrame#card { background: #171c28; border: 1px solid #2a3141; border-radius: 16px; }
QFrame#activityCard { background: #121722; border: 1px solid #252d3c; border-radius: 16px; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 22px; font-weight: 700; letter-spacing: -0.6px; }
QLabel#muted { color: #929caf; }
QLabel#eyebrow { color: #929caf; font-size: 11px; font-weight: 600; letter-spacing: 1.1px; }
QLabel#song { font-size: 32px; font-weight: 700; letter-spacing: -0.7px; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#route { color: #bac1d1; background: #1b2130; border: 1px solid #2c3445;
    border-radius: 15px; padding: 7px 13px; font-size: 11px; font-weight: 600; }
QLabel#status { color: #9ca9bc; font-size: 12px; }
QPushButton { background: #222a3b; color: #cbd2e0; border: 1px solid #354057;
    border-radius: 9px; padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: #2b354b; border-color: #55617b; color: #ffffff; }
QPushButton:pressed { background: #192131; }
QPushButton:disabled { color: #667085; background: #1a2030; border-color: #293044; }
QPushButton#primary { background: #9879ff; color: #11101a; border-color: #9879ff;
    padding: 12px 22px; font-weight: 700; }
QPushButton#primary:hover { background: #ae96ff; border-color: #ae96ff; }
QPushButton#primary:pressed { background: #8567e5; }
QPushButton#primary:disabled { background: #4b416b; color: #aaa1c1; border-color: #4b416b; }
QPushButton#ghost { border: none; background: transparent; color: #a6b0c5; padding: 8px 10px; }
QPushButton#ghost:hover { color: #d8d0ff; background: #22283a; }
QPushButton#browse { padding: 9px 14px; }
QLineEdit { background: #111722; color: #cad2e2; border: 1px solid #343e52;
    border-radius: 9px; padding: 11px 13px; selection-background-color: #6f56ba; }
QLineEdit:focus { border-color: #a38aff; background: #131a29; }
QLineEdit:disabled { color: #6f7a91; border-color: #293246; }
QSpinBox { background: #111722; border: 1px solid #343e52; border-radius: 7px;
    padding: 6px 12px; min-height: 21px; selection-background-color: #6f56ba; }
QSpinBox::up-button, QSpinBox::down-button { width: 20px; border: none; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px;
    background: #111722; border: 1px solid #46526a; }
QCheckBox::indicator:checked { background: #9879ff; border-color: #9879ff; }
QTableWidget { background: transparent; alternate-background-color: #1a2030;
    border: none; outline: 0; gridline-color: transparent; selection-background-color: #302a48;
    selection-color: #f2ecff; }
QTableWidget::item { padding: 10px; border-bottom: 1px solid #262e3e; }
QTableWidget::item:selected { background: #302a48; }
QHeaderView { background: transparent; }
QHeaderView::section { background: #171c28; color: #8794aa; font-size: 11px;
    font-weight: 600; border: none; padding: 10px; }
QTextEdit { background: transparent; color: #aab6ca; border: none;
    font-size: 12px; selection-background-color: #302a48; padding: 0; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 2px; }
QScrollBar::handle:vertical { background: #384257; border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip { background: #252d40; color: #edf0f7; border: 1px solid #48516a; padding: 6px; }
"""


def label(text, name=None):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    return result


class BridgeMark(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(44, 44)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#9879ff"))
        p.drawRoundedRect(QRectF(0, 0, 44, 44), 12, 12)
        pen = QPen(QColor("#161320"), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(11, 16, 32, 16)
        p.drawLine(28, 12, 32, 16)
        p.drawLine(28, 20, 32, 16)
        p.drawLine(12, 28, 33, 28)
        p.drawLine(12, 28, 16, 24)
        p.drawLine(12, 28, 16, 32)


class ProjectList(QScrollArea):
    """Real buttons keep each song accessible without Qt's virtual list cells."""
    projectSelected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("projectList")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.buttons = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.buttonToggled.connect(self.selected)
        content = QWidget()
        content.setObjectName("projectItems")
        self.items = QVBoxLayout(content)
        self.items.setContentsMargins(0, 0, 0, 0)
        self.items.setSpacing(8)
        self.items.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(content)

    def selected(self, button, checked):
        if checked:
            self.projectSelected.emit(button.property("projectId"))

    def update_project(self, pid, title, source, active):
        button = self.buttons.get(pid)
        if button is None:
            button = QPushButton()
            button.setObjectName("project")
            button.setProperty("projectId", pid)
            button.setCheckable(True)
            button.setFixedHeight(42)
            self.group.addButton(button)
            self.items.addWidget(button)
            self.buttons[pid] = button
        button.setText(button.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, 150))
        button.setAccessibleName(title)
        button.setToolTip(title + ("\n" + source if source else ""))
        if active:
            self.group.blockSignals(True)
            button.setChecked(True)
            self.group.blockSignals(False)


class Toggle(QCheckBox):
    def sizeHint(self):
        return QSize(210, 30)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#9879ff" if self.isChecked() else "#3b465b"))
        p.drawRoundedRect(QRectF(0, 5, 36, 20), 10, 10)
        p.setBrush(QColor("#f7f5ff" if self.isChecked() else "#a6b1c6"))
        p.drawEllipse(QRectF(19 if self.isChecked() else 3, 8, 14, 14))
        p.setPen(QColor("#dbe2f0"))
        p.drawText(QRectF(46, 0, self.width() - 46, 30), Qt.AlignmentFlag.AlignVCenter, self.text())


class Check(QCheckBox):
    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 31, 30)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#9879ff" if self.isChecked() else "#46526a"), 1))
        p.setBrush(QColor("#9879ff" if self.isChecked() else "#111722"))
        p.drawRoundedRect(QRectF(0.5, 6, 17, 17), 5, 5)
        if self.isChecked():
            pen = QPen(QColor("#161320"), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            check = QPainterPath()
            check.moveTo(4, 14)
            check.lineTo(7.5, 17.5)
            check.lineTo(13, 11)
            p.drawPath(check)
        p.setPen(QColor("#dbe2f0"))
        p.drawText(QRectF(26, 0, self.width() - 26, 30), Qt.AlignmentFlag.AlignVCenter, self.text())


def panel(name="card"):
    widget = QFrame()
    widget.setObjectName(name)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(12)
    return widget, layout


def build_window(w):
    w.setWindowTitle("DAWSync — Ableton ↔ REAPER")
    w.resize(1320, 900)
    w.setMinimumSize(1180, 720)
    w.setStyleSheet(THEME)
    root = QWidget()
    root.setObjectName("workspace")
    outer = QHBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(224)
    side = QVBoxLayout(sidebar)
    side.setContentsMargins(18, 26, 18, 20)
    side.setSpacing(16)
    brand = QHBoxLayout()
    brand.setSpacing(10)
    brand.addWidget(BridgeMark())
    brand.addWidget(label("DAWSync", "brand"))
    brand.addStretch()
    side.addLayout(brand)
    side.addWidget(label("Your studio, connected.", "muted"))
    side.addSpacing(22)
    side.addWidget(label("PROJECTS", "eyebrow"))
    w.projects_list = ProjectList()
    w.projects_list.setAccessibleName("Saved projects")
    side.addWidget(w.projects_list, 1)
    w.add_project_button = QPushButton("+  Add project")
    w.add_project_button.clicked.connect(w.add_project)
    side.addWidget(w.add_project_button)
    hint = label("Each song keeps its own\nsettings and revision history.", "muted")
    side.addWidget(hint)
    outer.addWidget(sidebar)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setObjectName("content")
    layout = QVBoxLayout(content)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    layout.setContentsMargins(28, 24, 28, 20)
    layout.setSpacing(20)

    header = QHBoxLayout()
    heading = QVBoxLayout()
    heading.setSpacing(5)
    w.song_name = label("Your next session", "song")
    heading.addWidget(w.song_name)
    w.summary = label("Connect a project to get started.", "muted")
    w.summary.setWordWrap(True)
    heading.addWidget(w.summary)
    header.addLayout(heading, 1)
    header.addSpacing(16)
    header.addWidget(label("ABLETON LIVE   ↔   REAPER", "route"), 0, Qt.AlignmentFlag.AlignTop)
    layout.addLayout(header)

    setup, setup_layout = panel()
    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(11)
    grid.setColumnStretch(1, 1)
    w.source = QLineEdit(w.config.get("source", ""))
    w.source.setPlaceholderText("Choose an Ableton Live project (.als)")
    w.exchange = QLineEdit(w.config.get("exchange", ""))
    w.exchange.setPlaceholderText("Choose the band's shared Google Drive folder")
    w.setup_buttons = []
    for row, (text, field, callback) in enumerate((("Ableton project", w.source, w.choose_source),
                                                  ("Shared folder", w.exchange, w.choose_exchange))):
        grid.addWidget(label(text, "muted"), row, 0)
        field.setFixedHeight(43)
        grid.addWidget(field, row, 1)
        b = QPushButton("Browse…")
        b.setObjectName("browse")
        b.setFixedHeight(43)
        b.clicked.connect(callback)
        w.setup_buttons.append(b)
        grid.addWidget(b, row, 2)
    setup_layout.addLayout(grid)

    options = QHBoxLayout()
    options.setSpacing(18)
    w.loop = Check("Use saved loop range")
    w.loop.setMinimumHeight(30)
    w.loop.setChecked(w.config.get("use_loop", True))
    w.loop.setToolTip("Uncheck to publish the whole Arrangement. The saved loop must start at 1.1.1.")
    options.addWidget(w.loop)
    options.addWidget(label("Effect tail", "muted"))
    w.tail = QSpinBox()
    w.tail.setRange(0, 60)
    w.tail.setSuffix(" sec")
    w.tail.setValue(w.config.get("tail", 4))
    w.tail.setFixedWidth(94)
    options.addWidget(w.tail)
    options.addStretch()
    w.auto = Toggle("Sync saved changes")
    w.auto.setFixedSize(210, 30)
    w.auto.setToolTip("Watch the selected project's saves and incoming revisions while it is open here.")
    w.auto.setChecked(False)
    options.addWidget(w.auto)
    setup_layout.addLayout(options)
    layout.addWidget(setup)

    actions = QHBoxLayout()
    actions.setSpacing(12)
    w.publish_button = QPushButton("Publish to REAPER  ↗")
    w.publish_button.setObjectName("primary")
    w.publish_button.setDefault(True)
    w.publish_button.clicked.connect(w.publish)
    actions.addWidget(w.publish_button)
    w.check_button = QPushButton("Check for updates")
    w.check_button.clicked.connect(w.scan)
    actions.addWidget(w.check_button)
    actions.addStretch()
    w.status = label("Ready · originals are preserved", "status")
    w.status.setWordWrap(True)
    w.status.setMinimumWidth(265)
    actions.addWidget(w.status, 1, Qt.AlignmentFlag.AlignRight)
    layout.addLayout(actions)

    revisions, rev_layout = panel()
    rev_header = QHBoxLayout()
    rev_header.addWidget(label("Shared revisions", "section"))
    rev_header.addStretch()
    rev_header.addWidget(label("Every version stays available", "muted"))
    rev_layout.addLayout(rev_header)
    w.table = QTableWidget(0, 4)
    w.table.setHorizontalHeaderLabels(["REVISION", "FROM", "AUDIO TRACKS", "STATUS"])
    w.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    w.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    w.table.verticalHeader().hide()
    w.table.verticalHeader().setDefaultSectionSize(38)
    w.table.setShowGrid(False)
    w.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    w.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    w.table.setMinimumHeight(184)
    rev_layout.addWidget(w.table, 1)
    rev_actions = QHBoxLayout()
    w.import_button = QPushButton("Import selected update")
    w.import_button.clicked.connect(w.import_selected)
    rev_actions.addWidget(w.import_button)
    w.open_button = QPushButton("Open Ableton return  ↗")
    w.open_button.setObjectName("ghost")
    w.open_button.clicked.connect(w.open_return)
    rev_actions.addWidget(w.open_button)
    rev_actions.addStretch()
    rev_layout.addLayout(rev_actions)
    layout.addWidget(revisions, 1)

    activity, activity_layout = panel("activityCard")
    activity_layout.setSpacing(8)
    activity_layout.addWidget(label("Recent activity", "section"))
    w.activity = QTextEdit()
    w.activity.setReadOnly(True)
    w.activity.setPlaceholderText("Your exports and incoming updates will appear here.")
    w.activity.setFixedHeight(44)
    activity_layout.addWidget(w.activity)
    layout.addWidget(activity)

    foot = QHBoxLayout()
    foot.addWidget(label("Audio travels. Originals stay safe.", "muted"))
    foot.addStretch()
    guide = QPushButton("Bandmate setup  ↗")
    guide.setObjectName("ghost")
    guide.clicked.connect(w.open_guide)
    foot.addWidget(guide)
    layout.addLayout(foot)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    w.setCentralWidget(root)
