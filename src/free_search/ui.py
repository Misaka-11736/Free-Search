"""Native desktop UI. All index/model work runs off the Qt UI thread."""

from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDateEdit, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSpinBox, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from .api import ApiClient, ApiConfig, Consent, load_key, save_key


class Job(QThread):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action

    def run(self):
        try:
            def progress(*parts):
                if self.isInterruptionRequested():
                    raise InterruptedError("已暂停；已完成文件仍可搜索，再次更新将复用它们。")
                self.progress.emit(" · ".join(map(str, parts)))
            value = self.action(progress)
            self.result.emit(value)
        except Exception as exc:
            self.error.emit(str(exc))


class ApiDialog(QDialog):
    def __init__(self, roots, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 设置与本次会话授权")
        self.setMinimumWidth(600)
        self.client = None
        self.roots = roots
        layout = QVBoxLayout(self)
        note = QLabel(
            "API 用于搜索结果的文本重排，索引始终在本机建立。\n"
            "兼容 POST /rerank（results: index + relevance_score）。\n"
            "每次最多发送查询和 20 个候选片段，每片段最多 2000 字符。\n"
            "图片和音视频选项仅授权其 OCR／转写文字；不发送原始媒体。\n"
            "授权只在本次运行中有效。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.endpoint = QLineEdit()
        self.endpoint.setPlaceholderText("https://服务商域名/v1")
        self.model = QLineEdit()
        self.model.setPlaceholderText("服务商提供的重排模型名称")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("可留空以读取此服务的 Windows 凭据")
        self.remember = QCheckBox("将密钥保存在系统凭据存储")
        self.request_limit = QSpinBox()
        self.request_limit.setRange(1, 10000)
        self.request_limit.setValue(100)
        self.text = QCheckBox("允许发送查询及所选目录内文档／源码的文本片段")
        self.images = QCheckBox("同时允许图片 OCR 文字外发")
        self.media = QCheckBox("同时允许音视频的转写／画面文字外发")
        form.addRow("API 基础地址", self.endpoint)
        form.addRow("重排模型", self.model)
        form.addRow("API 密钥", self.key)
        form.addRow("", self.remember)
        form.addRow("本次最多请求数", self.request_limit)
        form.addRow("", QLabel("本次外发总量上限 10 MiB；费用以服务商账单为准。"))
        layout.addLayout(form)
        layout.addWidget(self.text)
        layout.addWidget(self.images)
        layout.addWidget(self.media)
        scope = QTextEdit()
        scope.setReadOnly(True)
        scope.setMaximumHeight(90)
        scope.setPlainText("授权范围：\n" + "\n".join(roots))
        layout.addWidget(scope)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("启用本次 API 重排")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept_settings(self):
        if not self.text.isChecked():
            QMessageBox.information(self, "需要外发授权", "API 重排需要发送查询和候选片段，请先勾选文本授权。")
            return
        try:
            config = ApiConfig(self.endpoint.text().strip().rstrip("/"), self.model.text().strip(),
                               request_limit=self.request_limit.value())
            key = self.key.text().strip() or load_key(config)
            if self.remember.isChecked() and key:
                save_key(config, key)
            self.client = ApiClient(
                config, Consent(self.text.isChecked(), self.images.isChecked(),
                                self.media.isChecked(), tuple(self.roots)),
                edition="api", key=key,
            )
        except Exception as exc:
            QMessageBox.warning(self, "API 设置未保存", str(exc))
            return
        self.accept()


class SearchWindow(QMainWindow):
    def __init__(self, data_dir: Path, model_dir: Path, edition: str):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.model_dir = Path(model_dir)
        self.edition = edition
        self.api = None
        self.job = None
        self.image_path = None
        self.query_source = None
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("Free Search · " + ("完全离线版" if edition == "offline" else "API 版"))
        self.resize(1180, 850)
        base = QWidget()
        self.setCentralWidget(base)
        layout = QVBoxLayout(base)
        title_row = QHBoxLayout()
        title = QLabel("Free Search")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addWidget(QLabel("描述你要找的内容"))
        title_row.addStretch()
        self.mode = QLabel("全部在本机处理")
        title_row.addWidget(self.mode)
        self.api_button = QPushButton("API 设置")
        self.api_button.setVisible(edition == "api")
        self.api_button.clicked.connect(self.configure_api)
        title_row.addWidget(self.api_button)
        self.local_button = QPushButton("恢复本地")
        self.local_button.setVisible(False)
        self.local_button.clicked.connect(self.disable_api)
        title_row.addWidget(self.local_button)
        layout.addLayout(title_row)

        query_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(self.clear_query_source_if_empty)
        self.query.setPlaceholderText("例如：关于电池散热方案的文档，或包含某个报错的截图")
        self.query.returnPressed.connect(self.search)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.search)
        self.image_button = QPushButton("以图搜图")
        self.image_button.clicked.connect(self.choose_image)
        self.audio_button = QPushButton("语音文件提问")
        self.audio_button.clicked.connect(self.choose_audio)
        query_row.addWidget(self.query, 1)
        query_row.addWidget(self.image_button)
        query_row.addWidget(self.audio_button)
        query_row.addWidget(self.search_button)
        layout.addLayout(query_row)
        self.query_image_label = QLabel("")
        self.clear_image = QPushButton("取消图片")
        self.clear_image.clicked.connect(self.reset_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.query_image_label)
        image_row.addWidget(self.clear_image)
        image_row.addStretch()
        self.clear_image.hide()
        layout.addLayout(image_row)

        split = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 8, 0)
        side.addWidget(QLabel("索引目录"))
        self.roots = QListWidget()
        self.roots.setMaximumHeight(160)
        side.addWidget(self.roots)
        roots_row = QHBoxLayout()
        self.add_root = QPushButton("添加目录")
        self.add_root.clicked.connect(self.choose_root)
        self.remove_root = QPushButton("移除")
        self.remove_root.clicked.connect(self.remove_selected_root)
        roots_row.addWidget(self.add_root)
        roots_row.addWidget(self.remove_root)
        side.addLayout(roots_row)
        self.all_drives = QPushButton("添加所有固定磁盘")
        self.all_drives.clicked.connect(self.add_fixed_drives)
        side.addWidget(self.all_drives)
        self.image_index_button = QPushButton("先建图片索引（推荐）")
        self.image_index_button.clicked.connect(lambda: self.index(images_only=True))
        side.addWidget(self.image_index_button)
        self.index_button = QPushButton("补齐全部内容／增量更新")
        self.index_button.clicked.connect(self.index)
        side.addWidget(self.index_button)
        self.cancel_button = QPushButton("暂停索引")
        self.cancel_button.setToolTip("在内容整理或模型编码批次间暂停；正在解析的文件需等解析返回。")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.job.requestInterruption() if self.job else None)
        side.addWidget(self.cancel_button)
        side.addSpacing(12)
        side.addWidget(QLabel("结果过滤"))
        self.extensions = QLineEdit()
        self.extensions.setPlaceholderText("扩展名，如 .pdf,.docx")
        self.path_prefix = QLineEdit()
        self.path_prefix.setPlaceholderText("限制到目录（绝对路径）")
        side.addWidget(self.extensions)
        side.addWidget(self.path_prefix)
        self.after_check = QCheckBox("修改时间不早于")
        self.after = QDateEdit(QDate.currentDate().addDays(-30))
        self.after.setCalendarPopup(True)
        self.after.setDisplayFormat("yyyy-MM-dd")
        self.before_check = QCheckBox("修改时间不晚于")
        self.before = QDateEdit(QDate.currentDate())
        self.before.setCalendarPopup(True)
        self.before.setDisplayFormat("yyyy-MM-dd")
        side.addWidget(self.after_check)
        side.addWidget(self.after)
        side.addWidget(self.before_check)
        side.addWidget(self.before)
        side.addStretch()
        self.model_status = QLabel("正在检查本地模型…")
        self.model_status.setWordWrap(True)
        side.addWidget(self.model_status)
        split.addWidget(sidebar)

        content = QSplitter(Qt.Orientation.Vertical)
        self.results = QListWidget()
        self.results.setWordWrap(True)
        self.results.currentItemChanged.connect(self.show_result)
        self.results.itemDoubleClicked.connect(lambda _: self.open_selected())
        content.addWidget(self.results)
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        self.result_path = QLabel("选择结果查看命中内容与位置")
        self.result_path.setWordWrap(True)
        self.result_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_layout.addWidget(self.result_path)
        self.thumbnail = QLabel()
        self.thumbnail.setMaximumHeight(180)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.hide()
        preview_layout.addWidget(self.thumbnail)
        self.snippet = QTextEdit()
        self.snippet.setReadOnly(True)
        preview_layout.addWidget(self.snippet)
        open_row = QHBoxLayout()
        open_file = QPushButton("打开文件")
        open_file.clicked.connect(self.open_selected)
        open_folder = QPushButton("打开所在目录")
        open_folder.clicked.connect(lambda: self.open_selected(folder=True))
        open_row.addWidget(open_file)
        open_row.addWidget(open_folder)
        open_row.addStretch()
        preview_layout.addLayout(open_row)
        content.addWidget(preview)
        content.setSizes([360, 240])
        split.addWidget(content)
        split.setSizes([280, 850])
        layout.addWidget(split, 1)
        self.status = QLabel("添加目录并建立索引，然后开始搜索。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(5)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.setStyleSheet("""
            QMainWindow { background: #f5f7fb; }
            QWidget { font-family: "Microsoft YaHei UI"; font-size: 13px; color: #202b3b; }
            QLabel#title { font-size: 26px; font-weight: 700; color: #174a7c; padding: 4px 10px 10px 0; }
            QLineEdit, QListWidget, QTextEdit, QDateEdit, QSpinBox {
                background: white; border: 1px solid #d5deea; border-radius: 5px; padding: 7px;
            }
            QPushButton { background: #e8eef6; border: 1px solid #d1dce9; border-radius: 5px; padding: 8px 12px; }
            QPushButton:hover { background: #dce8f7; }
            QPushButton:disabled { color: #8b98a8; background: #edf0f4; }
            QPushButton#primary { background: #1864ab; color: white; border: 0; padding: 10px 24px; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #eef1f6; }
            QListWidget::item:selected { background: #e2eefc; color: #163e6b; }
        """)
        self.load_settings()
        self.start_job("检查本地索引与模型", self.inspect, self.inspected)

    def root_paths(self):
        return [self.roots.item(i).text() for i in range(self.roots.count())]

    def load_settings(self):
        path = self.data_dir / "ui_settings.json"
        if path.exists():
            try:
                for root in json.loads(path.read_text(encoding="utf-8")).get("roots", []):
                    self.roots.addItem(str(root))
            except (ValueError, OSError):
                self.status.setText("上次目录设置无法读取，请重新添加。")

    def save_settings(self):
        (self.data_dir / "ui_settings.json").write_text(
            json.dumps({"roots": self.root_paths()}, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    def choose_root(self):
        root = QFileDialog.getExistingDirectory(self, "选择需要索引的目录")
        if root:
            if str(Path(root)) not in self.root_paths():
                self.roots.addItem(str(Path(root)))
                self.save_settings()

    def remove_selected_root(self):
        if self.roots.currentRow() >= 0:
            self.roots.takeItem(self.roots.currentRow())
            self.save_settings()
            self.disable_api()
            self.status.setText("已从下次更新范围移除；已建立的索引仍可搜索。")

    def add_fixed_drives(self):
        import ctypes
        import string

        if os.name == "nt":
            drives = [f"{letter}:\\" for letter in string.ascii_uppercase
                      if ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 3]
        else:
            drives = ["/"]
        for root in drives:
            if root not in self.root_paths():
                self.roots.addItem(root)
        self.save_settings()
        self.status.setText("已添加固定磁盘。可先建图片索引并搜索照片，再补齐全部内容；首次全盘处理需要较长时间。")

    def with_engine(self, action):
        from .engine import SearchEngine

        engine = SearchEngine(self.data_dir, self.model_dir)
        try:
            return action(engine)
        finally:
            engine.close()

    def inspect(self, progress):
        return self.with_engine(lambda engine: {
            "stats": engine.stats(), "models": engine.models.availability(),
        })

    def inspected(self, result):
        models = result["models"]
        if isinstance(models, dict):
            labels = {"text_embedding": "文字语义", "text_reranker": "文字重排",
                      "vision": "图片语义", "speech": "语音识别", "ocr": "图片文字"}
            text = "本地组件：" + " / ".join(f"{labels.get(key,key)}{'✓' if value else '缺失'}" for key, value in models.items())
        else:
            text = str(models)
        self.model_status.setText(text)
        stats = result["stats"]
        self.status.setText(f"内容索引 {stats['files']} 个文件 · 仅文件名 {stats.get('metadata_only',0)} 个 · 处理失败 {stats['failed']} 个")

    def start_job(self, label, action, completed, cancellable=False):
        if self.job and self.job.isRunning():
            return
        self.set_busy(True)
        self.cancel_button.setEnabled(cancellable)
        self.status.setText(label)
        self.job = Job(action, self)
        self.job.progress.connect(self.status.setText)
        self.job.result.connect(completed)
        self.job.error.connect(self.show_error)
        self.job.finished.connect(self.job_finished)
        self.job.start()

    def job_finished(self):
        job = self.sender()
        if self.job is job:
            self.job = None
            self.set_busy(False)
        job.deleteLater()

    def set_busy(self, busy):
        self.cancel_button.setEnabled(False)
        for widget in [self.search_button, self.image_button, self.audio_button,
                       self.image_index_button, self.index_button, self.add_root, self.remove_root, self.all_drives,
                       self.api_button, self.local_button]:
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 1)

    def show_error(self, message):
        self.status.setText(message)
        QMessageBox.warning(self, "操作未完成", message)

    def index(self, images_only=False):
        roots = self.root_paths()
        if not roots:
            self.status.setText("请先添加索引目录。")
            return
        stage = "图片索引" if images_only else "全部内容索引"

        def action(progress):
            def report(stats):
                text = (f"{stage} · 已发现 {stats['discovered']} · 新建/更新 {stats['processed']}"
                        f" · 复用 {stats['unchanged']} · 失败 {stats['failed']}")
                if images_only:
                    text += f" · 待补齐的其他文件 {stats.get('deferred', 0)}"
                if stats.get("current_file"):
                    text += f"\n{Path(stats['current_file']).name} · {stats.get('phase', '')}"
                progress(text)
            return self.with_engine(lambda engine: engine.index(roots, progress=report, images_only=images_only))

        def completed(result):
            message = f"{stage}完成：新建/更新 {result['processed']}，复用 {result['unchanged']}，失败 {result['failed']}。"
            if images_only:
                message += " 可以先搜索照片；点击“补齐全部内容／增量更新”继续处理文档和音视频。"
            if result.get("enumeration_errors"):
                message += f" 有 {result['enumeration_errors']} 处目录无法完整读取。"
            self.status.setText(message)

        self.start_job(
            f"开始{stage}，检查文件变化…", action, completed,
            cancellable=True,
        )

    def filters(self):
        result = {}
        if self.extensions.text().strip():
            result["ext"] = self.extensions.text().strip()
        if self.path_prefix.text().strip():
            result["path_prefix"] = self.path_prefix.text().strip()
        if self.after_check.isChecked():
            result["modified_after"] = datetime.combine(self.after.date().toPython(), time.min).timestamp()
        if self.before_check.isChecked():
            result["modified_before"] = datetime.combine(
                self.before.date().toPython() + timedelta(days=1), time.min,
            ).timestamp()
        return result

    def search(self):
        query = self.query.text().strip()
        image_path = self.image_path
        if not query and not image_path:
            self.status.setText("请输入搜索描述，或选择一张图片。")
            return
        filters = self.filters()
        if (filters.get("modified_after", float("-inf"))
                >= filters.get("modified_before", float("inf"))):
            self.status.setText("修改时间的起始日期不能晚于结束日期。")
            return
        api = self.api
        query_source = dict(self.query_source) if self.query_source is not None else None

        def action(engine):
            engine.api = api
            return engine.search(query, filters=filters, limit=20, image_path=image_path,
                                 query_source=query_source)

        self.start_job("正在查找相关文件…", lambda progress: self.with_engine(action), self.found)

    def found(self, results):
        self.results.clear()
        for index, result in enumerate(results):
            path = Path(result["path"])
            location = str(result.get("locator", ""))
            text = str(result.get("text", "")).replace("\n", " ")[:160]
            item = QListWidgetItem(f"{index + 1}. {path.name}\n{path.parent}\n{location} · {text}")
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.results.addItem(item)
        self.status.setText(f"找到 {len(results)} 个候选文件，按相关性排序。")
        if results:
            self.results.setCurrentRow(0)
        else:
            self.result_path.setText("没有找到候选文件")
            self.snippet.setPlainText("请检查索引是否完成，或调整查询描述与过滤条件。")
            self.thumbnail.hide()
        if self.api:
            self.mode.setText(f"API 已启用 · 本次 {self.api.requests}/{self.api.config.request_limit} 次请求")

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择查询图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.image_path = path
            self.query_image_label.setText("查询图片：" + Path(path).name)
            self.clear_image.show()

    def reset_image(self):
        self.image_path = None
        self.query_image_label.clear()
        self.clear_image.hide()

    def choose_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择语音问题录音", "", "音频 (*.wav *.mp3 *.m4a *.flac *.ogg);;所有文件 (*)",
        )
        if not path:
            return
        self.start_job(
            "正在本地识别语音问题…",
            lambda progress: self.with_engine(lambda engine: engine.models.transcribe(path)),
            lambda segments: self.transcribed(segments, path),
        )

    def transcribed(self, segments, path):
        text = " ".join(str(segment.get("text", "")) for segment in segments).strip()
        self.query_source = {"path": str(Path(path).resolve()), "modality": "audio"} if text else None
        self.query.setText(text)
        self.status.setText("语音已识别，请检查文字后点击搜索。" if text else "录音中未识别到讲话内容。")

    def clear_query_source_if_empty(self, text):
        # Edits can still contain material from the recording; only an explicit
        # clear starts a new typed query without that provenance.
        if not text:
            self.query_source = None

    def show_result(self, item, previous=None):
        self.thumbnail.hide()
        if item is None:
            return
        result = item.data(Qt.ItemDataRole.UserRole)
        path = Path(result["path"])
        self.result_path.setText(str(path))
        self.snippet.setPlainText(
            f"命中位置：{result.get('locator', '')}\n内容类型：{result.get('modality', '')}\n\n"
            + str(result.get("text", "")),
        )
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            reader.setScaledSize(reader.size().scaled(700, 180, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if not image.isNull():
                self.thumbnail.setPixmap(QPixmap.fromImage(image))
                self.thumbnail.show()

    def open_selected(self, checked=False, folder=False):
        item = self.results.currentItem()
        if item:
            path = Path(item.data(Qt.ItemDataRole.UserRole)["path"])
            target = path.parent if folder else path
            if not target.exists():
                self.status.setText("文件已移动或删除，请增量更新索引。")
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def configure_api(self):
        if self.edition != "api":
            return
        roots = self.root_paths()
        if not roots:
            self.status.setText("请先添加目录，以便限定 API 的外发范围。")
            return
        dialog = ApiDialog(roots, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.api = dialog.client
            self.mode.setText("已授权 API 文本重排 · 仅本次会话")
            self.local_button.show()

    def disable_api(self):
        self.api = None
        self.mode.setText("全部在本机处理")
        self.local_button.hide()

    def closeEvent(self, event):
        if self.job and self.job.isRunning():
            QMessageBox.information(self, "正在处理", "后台任务仍在处理，请等待当前任务完成后关闭。")
            event.ignore()
        else:
            self.save_settings()
            event.accept()


def run(data_dir: Path, model_dir: Path, edition: str = "offline") -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Free Search")
    window = SearchWindow(data_dir, model_dir, edition)
    window.show()
    return app.exec()
