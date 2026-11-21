"""Janela principal do IDEF-SIM Studio."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QGraphicsView,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressDialog, QToolBar)

from .. import __version__
from ..examples import ALL as EXAMPLES
from ..model import CONNECTION_LABELS, KIND_LABELS, ConnectionKind as CK, ElementKind as EK, Model
from ..report import model_to_html
from ..simulation import SimulationError, run_simulation
from ..storage import FILE_EXTENSION, load_model, save_model
from ..validation import ERROR, INFO, WARNING, validate
from . import shapes
from .dialogs import LegendDialog, ResultsDialog
from .items import EdgeItem, NodeItem
from .properties import PropertiesPanel
from .scene import DiagramScene

FILE_FILTER = f"Modelos IDEF-SIM (*{FILE_EXTENSION});;Todos os ficheiros (*)"
MAX_HISTORY = 200


class DiagramView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
            self.scale(f, f)
        else:
            super().wheelEvent(ev)


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.settings = QSettings("IDEF-SIM Studio", "IDEF-SIM Studio")
        self.path: Path | None = None
        self.dirty = False
        self.history: list[str] = []
        self.hist_keys: list[str] = []
        self.hist_idx = -1

        self.scene = DiagramScene(Model())
        self.view = DiagramView(self.scene)
        self.setCentralWidget(self.view)
        self.resize(1400, 860)

        self.props = PropertiesPanel()
        dock = QDockWidget("Propriedades", self)
        dock.setObjectName("props")
        dock.setWidget(self.props)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        self.issues = QListWidget()
        self.issues.itemActivated.connect(self._issue_clicked)
        self.issues.itemClicked.connect(self._issue_clicked)
        self.issue_dock = QDockWidget("Validação", self)
        self.issue_dock.setObjectName("issues")
        self.issue_dock.setWidget(self.issues)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.issue_dock)

        self._build_actions()
        self._build_menus()
        self._build_palette()

        self.scene.modelChanged.connect(self._on_model_changed)
        self.scene.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.scene.selectionChanged.connect(self._on_selection)
        self.scene.toolFinished.connect(lambda: self.tool_actions["select"].setChecked(True))
        self.props.edited.connect(self._on_props_edited)
        self.props.elementRenamed.connect(self.scene.refresh_element)

        if path:
            self.open_file(path)
        else:
            self._reset_history()
            self._on_selection()
        self._update_title()
        self.statusBar().showMessage("Escolha um símbolo na paleta e clique no diagrama. "
                                     "Shift mantém a ferramenta ativa; Esc ou botão direito cancela.")

    # ---------------------------------------------------------------- ações
    def _act(self, text, slot, shortcut=None, tip=None, icon=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setStatusTip(tip)
        if icon is not None:
            a.setIcon(icon)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        S = QKeySequence.StandardKey
        self.a_new = self._act("&Novo", self.new_model, S.New)
        self.a_open = self._act("&Abrir…", lambda: self.open_file(), S.Open)
        self.a_save = self._act("&Guardar", self.save, S.Save)
        self.a_save_as = self._act("Guardar &como…", self.save_as, S.SaveAs)
        self.a_png = self._act("Exportar imagem PNG…", lambda: self.export_image("png"))
        self.a_svg = self._act("Exportar imagem SVG…", lambda: self.export_image("svg"))
        self.a_html = self._act("Exportar documentação HTML…", self.export_html)
        self.a_quit = self._act("&Sair", self.close, S.Quit)
        self.a_undo = self._act("&Desfazer", self.undo, S.Undo)
        self.a_redo = self._act("&Refazer", self.redo, S.Redo)
        self.a_del = self._act("&Eliminar", self.scene.delete_selected, S.Delete)
        self.a_dup = self._act("D&uplicar", self.scene.duplicate_selected, "Ctrl+D")
        self.a_all = self._act("Selecionar &tudo", self._select_all, S.SelectAll)
        self.a_zin = self._act("Ampliar", lambda: self.view.scale(1.2, 1.2), S.ZoomIn)
        self.a_zout = self._act("Reduzir", lambda: self.view.scale(1 / 1.2, 1 / 1.2), S.ZoomOut)
        self.a_fit = self._act("Ajustar à janela", self.fit, "Ctrl+0")
        self.a_validate = self._act("&Validar modelo", self.validate, "F7")
        self.a_run = self._act("&Executar simulação", self.run_sim, "F5")
        self.a_props = self._act("Propriedades do &modelo", self._show_model_props, "Ctrl+M")
        self.a_legend = self._act("Notação IDEF-SIM", lambda: LegendDialog(self).exec(), "F1")
        self.a_about = self._act("Sobre", self.about)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&Ficheiro")
        m.addActions([self.a_new, self.a_open])
        self.recent_menu = m.addMenu("Abrir &recente")
        ex = m.addMenu("Abrir &exemplo")
        for name, fn in EXAMPLES.items():
            ex.addAction(self._act(name, lambda _=False, fn=fn: self._load_example(fn)))
        m.addSeparator()
        m.addActions([self.a_save, self.a_save_as])
        m.addSeparator()
        m.addActions([self.a_png, self.a_svg, self.a_html])
        m.addSeparator()
        m.addAction(self.a_quit)
        m = mb.addMenu("&Editar")
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_dup, self.a_del, self.a_all])
        m = mb.addMenu("&Ver")
        m.addActions([self.a_zin, self.a_zout, self.a_fit])
        m = mb.addMenu("&Modelo")
        m.addActions([self.a_props, self.a_validate])
        m = mb.addMenu("&Simulação")
        m.addAction(self.a_run)
        m = mb.addMenu("A&juda")
        m.addActions([self.a_legend, self.a_about])
        self._refresh_recent()

        tb = QToolBar("Principal")
        tb.setObjectName("main")
        tb.addActions([self.a_new, self.a_open, self.a_save])
        tb.addSeparator()
        tb.addActions([self.a_undo, self.a_redo, self.a_del])
        tb.addSeparator()
        tb.addActions([self.a_fit, self.a_validate, self.a_run])
        self.addToolBar(tb)

    def _build_palette(self):
        tb = QToolBar("Paleta IDEF-SIM")
        tb.setObjectName("palette")
        tb.setIconSize(QSize(26, 26))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.LeftToolBarArea, tb)
        grp = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}

        def add(key, text, icon, tool, kind, shortcut=None):
            a = QAction(icon, text.replace("&", "&&"), self)
            a.setCheckable(True)
            if shortcut:
                a.setShortcut(shortcut)
            a.setToolTip(f"{text} ({shortcut})" if shortcut else text)
            a.triggered.connect(lambda: self.scene.set_tool(tool, kind))
            grp.addAction(a)
            tb.addAction(a)
            self.tool_actions[key] = a

        sel = QAction("Selecionar", self)
        add("select", "Selecionar", sel.icon(), "select", None, "V")
        self.tool_actions["select"].setChecked(True)
        tb.addSeparator()
        keys = {EK.ENTITY: "E", EK.FUNCTION: "F", EK.RESOURCE: "R", EK.CONTROL: "C",
                EK.MOVEMENT: "M", EK.RULE_AND: "1", EK.RULE_OR: "2", EK.RULE_ANDOR: "3",
                EK.EXIT: "X", EK.CONNECTOR: "K", EK.NOTE: "N"}
        for kind in EK:
            add(kind.value, KIND_LABELS[kind], shapes.element_icon(kind), "add", kind, keys[kind])
        tb.addSeparator()
        lkeys = {CK.FLOW: "L", CK.RESOURCE: "Shift+R", CK.CONTROL: "Shift+C", CK.NOTE: "Shift+N"}
        for ck in CK:
            add("link_" + ck.value, CONNECTION_LABELS[ck], shapes.connection_icon(ck), "link", ck, lkeys[ck])

    # ---------------------------------------------------------- histórico
    def _snapshot(self) -> str:
        return json.dumps(self.scene.model.to_dict(), ensure_ascii=False)

    def _reset_history(self):
        self.history = [self._snapshot()]
        self.hist_keys = [""]
        self.hist_idx = 0
        self._update_undo()

    def _commit(self, desc: str, key: str = ""):
        snap = self._snapshot()
        if snap == self.history[self.hist_idx]:
            return
        del self.history[self.hist_idx + 1:]
        del self.hist_keys[self.hist_idx + 1:]
        if key and self.hist_keys[self.hist_idx] == key and self.hist_idx > 0:
            self.history[self.hist_idx] = snap
        else:
            self.history.append(snap)
            self.hist_keys.append(key)
            if len(self.history) > MAX_HISTORY:
                self.history.pop(0)
                self.hist_keys.pop(0)
            self.hist_idx = len(self.history) - 1
        self._set_dirty(True)
        self._update_undo()
        self._live_validate()

    def _restore(self, idx: int):
        self.hist_idx = idx
        self.hist_keys[idx] = ""
        self.scene.set_model(Model.from_dict(json.loads(self.history[idx])))
        self._set_dirty(True)
        self._update_undo()
        self._on_selection()
        self._live_validate()

    def undo(self):
        if self.hist_idx > 0:
            self._restore(self.hist_idx - 1)

    def redo(self):
        if self.hist_idx < len(self.history) - 1:
            self._restore(self.hist_idx + 1)

    def _update_undo(self):
        self.a_undo.setEnabled(self.hist_idx > 0)
        self.a_redo.setEnabled(self.hist_idx < len(self.history) - 1)

    # ----------------------------------------------------------- eventos
    def _on_model_changed(self, desc: str, key: str):
        self._commit(desc, key)
        self._on_selection()

    def _on_props_edited(self, desc: str, key: str):
        self._commit(desc, key)
        if key.startswith("model.name"):
            self._update_title()

    def _on_selection(self):
        try:
            sel = self.scene.selectedItems()
        except RuntimeError:
            return
        m = self.scene.model
        if len(sel) == 1 and isinstance(sel[0], NodeItem):
            self.props.show_element(m, sel[0].element)
        elif len(sel) == 1 and isinstance(sel[0], EdgeItem):
            self.props.show_connection(m, sel[0].conn)
        else:
            self.props.show_model(m)

    def _show_model_props(self):
        self.scene.clearSelection()
        self.props.show_model(self.scene.model)

    def _select_all(self):
        for it in self.scene.items():
            if isinstance(it, (NodeItem, EdgeItem)):
                it.setSelected(True)

    def _issue_clicked(self, item: QListWidgetItem):
        eid = item.data(Qt.UserRole)
        if eid:
            self.scene.select_element(eid)

    # ---------------------------------------------------------- ficheiros
    def _set_dirty(self, d: bool):
        self.dirty = d
        self._update_title()

    def _update_title(self):
        name = self.path.name if self.path else "sem título"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{self.scene.model.name} [{name}] — IDEF-SIM Studio")

    def _maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Alterações por guardar",
                                 "O modelo tem alterações por guardar. Deseja guardá-las?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def _set_model(self, model: Model, path: Path | None):
        self.scene.set_model(model)
        self.path = path
        self._reset_history()
        self._set_dirty(False)
        self._on_selection()
        self.fit()
        self._live_validate()

    def new_model(self):
        if self._maybe_save():
            self._set_model(Model(), None)

    def _load_example(self, fn):
        if self._maybe_save():
            self._set_model(fn(), None)

    def open_file(self, path: str | None = None):
        if path is None:
            if not self._maybe_save():
                return
            path, _ = QFileDialog.getOpenFileName(self, "Abrir modelo", self._last_dir(), FILE_FILTER)
            if not path:
                return
        try:
            model = load_model(path)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Erro ao abrir", f"Não foi possível abrir o ficheiro:\n{ex}")
            return
        self._set_model(model, Path(path))
        self._add_recent(path)

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        try:
            save_model(self.scene.model, self.path)
        except OSError as ex:
            QMessageBox.critical(self, "Erro ao guardar", str(ex))
            return False
        self._set_dirty(False)
        self._add_recent(str(self.path))
        self.statusBar().showMessage(f"Guardado em {self.path}", 4000)
        return True

    def save_as(self) -> bool:
        default = str(Path(self._last_dir()) / (self.scene.model.name + FILE_EXTENSION))
        path, _ = QFileDialog.getSaveFileName(self, "Guardar modelo", default, FILE_FILTER)
        if not path:
            return False
        if not path.endswith(FILE_EXTENSION):
            path += FILE_EXTENSION
        self.path = Path(path)
        return self.save()

    def _last_dir(self) -> str:
        return str(self.settings.value("last_dir", str(Path.home())))

    def _add_recent(self, path: str):
        rec = [p for p in (self.settings.value("recent", []) or []) if p != path]
        rec.insert(0, path)
        self.settings.setValue("recent", rec[:10])
        self.settings.setValue("last_dir", str(Path(path).parent))
        self._refresh_recent()

    def _refresh_recent(self):
        self.recent_menu.clear()
        rec = self.settings.value("recent", []) or []
        if isinstance(rec, str):
            rec = [rec]
        for p in rec:
            self.recent_menu.addAction(self._act(p, lambda _=False, p=p: self._open_recent(p)))
        self.recent_menu.setEnabled(bool(rec))

    def _open_recent(self, p):
        if self._maybe_save():
            self.open_file(p)

    def closeEvent(self, ev):
        if self._maybe_save():
            ev.accept()
        else:
            ev.ignore()

    # ---------------------------------------------------------- exportação
    def _diagram_rect(self) -> QRectF:
        return self.scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)

    def _render(self, painter, rect):
        sel = self.scene.selectedItems()
        self.scene.clearSelection()
        self.scene.show_grid = False
        self.scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
        self.scene.show_grid = True
        for it in sel:
            it.setSelected(True)

    def svg_bytes(self) -> bytes:
        rect = self._diagram_rect()
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        gen = QSvgGenerator()
        gen.setOutputDevice(buf)
        gen.setSize(rect.size().toSize())
        gen.setViewBox(QRectF(0, 0, rect.width(), rect.height()))
        gen.setTitle(self.scene.model.name)
        p = QPainter(gen)
        self._render(p, rect)
        p.end()
        return bytes(buf.data())

    def image(self, scale: float = 2.0) -> QImage:
        rect = self._diagram_rect()
        img = QImage(int(rect.width() * scale), int(rect.height() * scale), QImage.Format_ARGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(scale, scale)
        self._render(p, rect)
        p.end()
        return img

    def export_image(self, fmt: str):
        if not self.scene.model.elements:
            return
        default = str(Path(self._last_dir()) / f"{self.scene.model.name}.{fmt}")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar diagrama", default, f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        if fmt == "svg":
            Path(path).write_bytes(self.svg_bytes())
        else:
            self.image().save(path)
        self.statusBar().showMessage(f"Exportado para {path}", 4000)

    def export_html(self):
        default = str(Path(self._last_dir()) / f"{self.scene.model.name}.html")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar documentação", default, "HTML (*.html)")
        if not path:
            return
        svg = self.svg_bytes().decode("utf-8", "replace") if self.scene.model.elements else None
        if svg and "<svg" in svg:
            svg = svg[svg.index("<svg"):]
        Path(path).write_text(model_to_html(self.scene.model, svg), encoding="utf-8")
        self.statusBar().showMessage(f"Documentação exportada para {path}", 4000)

    # --------------------------------------------------- validação/simulação
    def _live_validate(self):
        self._show_issues(validate(self.scene.model))

    def _show_issues(self, issues):
        self.issues.clear()
        icons = {ERROR: "⛔", WARNING: "⚠️", INFO: "ℹ️"}
        for i in issues:
            it = QListWidgetItem(f"{icons[i.level]}  {i.message}")
            it.setData(Qt.UserRole, i.element_id)
            self.issues.addItem(it)
        n_err = sum(i.level == ERROR for i in issues)
        n_warn = sum(i.level == WARNING for i in issues)
        self.issue_dock.setWindowTitle(f"Validação — {n_err} erro(s), {n_warn} aviso(s)")
        if not issues:
            self.issues.addItem("✅  Nenhum problema encontrado.")

    def validate(self):
        issues = validate(self.scene.model)
        self._show_issues(issues)
        self.issue_dock.show()
        self.issue_dock.raise_()
        return issues

    def run_sim(self):
        issues = self.validate()
        if any(i.level == ERROR for i in issues):
            QMessageBox.warning(self, "Simulação", "Corrija os erros indicados no painel de "
                                                   "Validação antes de simular.")
            return
        n = self.scene.model.settings.replications
        dlg = QProgressDialog("A simular…", "Cancelar", 0, n, self)
        dlg.setWindowTitle("Simulação")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progress(i, total):
            dlg.setValue(i)
            dlg.setLabelText(f"Replicação {min(i + 1, total)} de {total}…")
            QApplication.processEvents()
            return not dlg.wasCanceled()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = run_simulation(self.scene.model, progress)
        except SimulationError as ex:
            QMessageBox.warning(self, "Simulação", str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Erro na simulação", repr(ex))
            return
        finally:
            QApplication.restoreOverrideCursor()
            dlg.close()
        if not result.replications:
            return
        ResultsDialog(result, self).exec()

    # ------------------------------------------------------------- outros
    def fit(self):
        if self.scene.model.elements:
            self.view.fitInView(self._diagram_rect(), Qt.KeepAspectRatio)
            t = self.view.transform()
            if t.m11() > 1.3:
                self.view.resetTransform()
                self.view.scale(1.3, 1.3)
                self.view.centerOn(self._diagram_rect().center())

    def about(self):
        QMessageBox.about(self, "Sobre o IDEF-SIM Studio",
                          f"<h3>IDEF-SIM Studio {__version__}</h3>"
                          "<p>Ferramenta para criar, documentar, validar e simular modelos "
                          "conceituais na técnica IDEF-SIM para simulação a eventos discretos.</p>"
                          "<p>Referência: LEAL, F.; ALMEIDA, D. A.; MONTEVECHI, J. A. B. "
                          "<i>Uma proposta de técnica de modelagem conceitual para a simulação "
                          "através de elementos do IDEF</i>. SBPO, 2008.</p>")
