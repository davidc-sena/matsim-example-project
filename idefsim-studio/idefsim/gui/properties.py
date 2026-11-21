"""Painel de propriedades do modelo, elemento ou ligação selecionada."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import distributions as dist
from ..model import (CONNECTION_LABELS, KIND_LABELS, Connection, ConnectionKind as CK,
                     Element, ElementKind as EK, Model, PROCESS_KINDS)

DIST_HELP = ("Distribuições aceites:\n" + "\n".join(dist.SUPPORTED)
             + "\n\nUse ';' para separar argumentos com vírgula decimal, ex.: NORM(5,5; 0,8)")


class _TextEdit(QPlainTextEdit):
    editingFinished = Signal()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.editingFinished.emit()


class PropertiesPanel(QScrollArea):
    edited = Signal(str, str)        # descrição, chave de agrupamento
    elementRenamed = Signal(str)     # id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(280)
        self.model: Model | None = None
        self._clear()

    def _clear(self) -> QFormLayout:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:bold;font-size:11pt;padding:4px 0")
        lay.addWidget(self.title)
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        lay.addLayout(self.form)
        lay.addStretch(1)
        self.setWidget(w)
        return self.form

    # --------------------------------------------------------------- helpers
    def _line(self, label, value, apply, tip="", validator=None):
        ed = QLineEdit(str(value))
        ed.setToolTip(tip)

        def check():
            ok = validator is None or validator(ed.text())
            ed.setStyleSheet("" if ok else "background:#ffd9d9")
            return ok

        def done():
            if check() and ed.text() != str(value_holder[0]):
                value_holder[0] = ed.text()
                apply(ed.text())
        value_holder = [value]
        ed.textChanged.connect(lambda _: check())
        ed.editingFinished.connect(done)
        check()
        self.form.addRow(label, ed)
        return ed

    def _spin(self, label, value, apply, lo=0, hi=10**9, tip=""):
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(int(value))
        sp.setToolTip(tip)
        sp.valueChanged.connect(apply)
        self.form.addRow(label, sp)
        return sp

    def _dspin(self, label, value, apply, lo=0.0, hi=1e9, step=1.0, dec=2):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(dec)
        sp.setSingleStep(step)
        sp.setValue(float(value))
        sp.valueChanged.connect(apply)
        self.form.addRow(label, sp)
        return sp

    def _text(self, label, value, apply):
        ed = _TextEdit(value)
        ed.setFixedHeight(80)
        ed.editingFinished.connect(lambda: ed.toPlainText() != value and apply(ed.toPlainText()))
        self.form.addRow(label, ed)
        return ed

    # ------------------------------------------------------------------ modelo
    def show_model(self, model: Model) -> None:
        self.model = model
        self._clear()
        self.title.setText("Modelo")
        s = model.settings

        def setter(obj, attr, desc, conv=lambda v: v):
            def f(v):
                setattr(obj, attr, conv(v))
                self.edited.emit(desc, f"model.{attr}")
            return f

        self._line("Nome", model.name, setter(model, "name", "Nome do modelo"))
        self._line("Autor", model.author, setter(model, "author", "Autor"))
        self._line("Versão", model.version, setter(model, "version", "Versão"))
        self._text("Descrição", model.description, setter(model, "description", "Descrição"))
        sep = QLabel("<b>Simulação</b>")
        self.form.addRow(sep)
        unit = QComboBox()
        unit.setEditable(True)
        unit.addItems(["s", "min", "h", "dia"])
        unit.setCurrentText(s.time_unit)
        unit.currentTextChanged.connect(setter(s, "time_unit", "Unidade de tempo"))
        self.form.addRow("Unidade de tempo", unit)
        self._dspin("Duração", s.duration, setter(s, "duration", "Duração"), 0.01, 1e9, 60)
        self._dspin("Aquecimento", s.warmup, setter(s, "warmup", "Aquecimento"), 0, 1e9, 10)
        self._spin("Replicações", s.replications, setter(s, "replications", "Replicações"), 1, 1000)
        self._spin("Semente", s.seed, setter(s, "seed", "Semente"), 0, 2**31 - 1)
        n_el = len(model.elements)
        self.form.addRow(QLabel(f"<i>{n_el} elementos, {len(model.connections)} ligações.<br>"
                                "Selecione um elemento para editar as suas propriedades.</i>"))

    # ---------------------------------------------------------------- elemento
    def show_element(self, model: Model, e: Element) -> None:
        self.model = model
        self._clear()
        self.title.setText(KIND_LABELS[e.kind])

        def set_name(v):
            e.name = v.strip() or e.name
            self.elementRenamed.emit(e.id)
            self.edited.emit("Renomear", f"{e.id}.name")

        def set_param(key, desc, conv=lambda v: v):
            def f(v):
                e.params[key] = conv(v)
                self.elementRenamed.emit(e.id)
                self.edited.emit(desc, f"{e.id}.{key}")
            return f

        def set_desc(v):
            e.description = v
            self.elementRenamed.emit(e.id)
            self.edited.emit("Descrição", f"{e.id}.description")

        if e.kind not in (EK.RULE_AND, EK.RULE_OR, EK.RULE_ANDOR):
            self._line("Nome", e.name, set_name,
                       "Conectores com o mesmo nome ligam-se entre si." if e.kind == EK.CONNECTOR else "")
        else:
            self.form.addRow(QLabel(self._rule_help(e.kind)))

        if e.kind == EK.ENTITY:
            if model.incoming(e.id):
                self.form.addRow(QLabel("<i>Entidade de transformação: as entidades que chegam "
                                        "passam a ser deste tipo.</i>"))
            else:
                self._line("Intervalo entre chegadas", e.params.get("interarrival", ""),
                           set_param("interarrival", "Intervalo entre chegadas"), DIST_HELP, dist.is_valid)
                self._line("Primeira chegada", e.params.get("first_arrival", "0"),
                           set_param("first_arrival", "Primeira chegada"), DIST_HELP, dist.is_valid)
                self._spin("Entidades por chegada", e.params.get("batch_size", 1),
                           set_param("batch_size", "Lote"), 1, 10**6)
                self._spin("Máx. de chegadas", e.params.get("max_arrivals", 0),
                           set_param("max_arrivals", "Máx. chegadas"), 0, 10**9, "0 = ilimitado")
        elif e.kind in PROCESS_KINDS:
            self._line("Tempo" + (" de processamento" if e.kind == EK.FUNCTION else " de deslocação"),
                       e.params.get("duration", ""), set_param("duration", "Tempo"), DIST_HELP, dist.is_valid)
            res = model.resources_of(e.id)
            self.form.addRow("Recursos", QLabel(", ".join(r.name for r in res) or
                                                "<i>nenhum (capacidade infinita)</i>"))
            ctrls = [model.elements[c.source].name for c in model.incoming(e.id, CK.CONTROL)]
            if ctrls:
                self.form.addRow("Controles", QLabel(", ".join(ctrls)))
        elif e.kind == EK.RESOURCE:
            self._spin("Capacidade", e.params.get("capacity", 1),
                       set_param("capacity", "Capacidade", int), 1, 10**6)
            used = [model.elements[c.target].name for c in model.outgoing(e.id, CK.RESOURCE)]
            self.form.addRow("Usado em", QLabel(", ".join(used) or "<i>—</i>"))

        self._text("Descrição", e.description, set_desc)
        outs = model.outgoing(e.id)
        if len(outs) > 1:
            self.form.addRow(QLabel("<b>Saídas</b>"))
            for c in outs:
                self._prob_row(model, c, model.elements[c.target].name)

    @staticmethod
    def _rule_help(kind: EK) -> str:
        return {
            EK.RULE_AND: "<b>&amp; (E)</b>: com várias entradas aguarda uma entidade de cada "
                         "ramo (junção/montagem); com várias saídas segue todos os ramos.",
            EK.RULE_OR: "<b>X (OU)</b>: a entidade segue apenas uma das saídas, escolhida "
                        "pelas probabilidades.",
            EK.RULE_ANDOR: "<b>O (E/OU)</b>: cada saída é seguida de forma independente "
                           "com a sua probabilidade.",
        }[kind]

    def _prob_row(self, model, c: Connection, name: str):
        def f(v, c=c):
            c.probability = v / 100
            self.elementRenamed.emit(c.source)
            self.edited.emit("Probabilidade", f"{c.id}.p")
        self._dspin(f"→ {name} (%)", c.probability * 100, f, 0, 100, 5, 2)

    # ----------------------------------------------------------------- ligação
    def show_connection(self, model: Model, c: Connection) -> None:
        self.model = model
        self._clear()
        self.title.setText(CONNECTION_LABELS[c.kind])
        s, t = model.elements[c.source], model.elements[c.target]
        self.form.addRow("De", QLabel(s.name))
        self.form.addRow("Para", QLabel(t.name))

        def set_label(v):
            c.label = v
            self.elementRenamed.emit(c.source)
            self.edited.emit("Rótulo", f"{c.id}.label")
        self._line("Rótulo", c.label, set_label)
        if c.kind == CK.FLOW and len(model.outgoing(c.source)) > 1 or s.kind == EK.RULE_ANDOR:
            self._prob_row(model, c, "probabilidade")
