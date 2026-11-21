"""Diálogos: resultados de simulação e legenda da notação IDEF-SIM."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ..model import ConnectionKind as CK, ElementKind as EK
from ..simulation import SimulationResult
from . import shapes


def _fmt(v: float) -> str:
    if v != v:
        return "—"
    return f"{v:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ResultsDialog(QDialog):
    def __init__(self, result: SimulationResult, parent=None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle(f"Resultados — {result.model_name}")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        n = len(result.replications)
        lay.addWidget(QLabel(
            f"<b>{result.model_name}</b> — {n} replicação(ões), duração {result.duration:g} "
            f"{result.time_unit}, aquecimento {result.warmup:g} {result.time_unit}. "
            "IC 95% calculado com t de Student entre replicações."))
        top = QHBoxLayout()
        top.addWidget(QLabel("Filtrar categoria:"))
        self.filter = QComboBox()
        self.rows = result.rows()
        self.filter.addItems(["Todas"] + sorted({r.category for r in self.rows},
                                                key=[r.category for r in self.rows].index))
        self.filter.currentTextChanged.connect(self._fill)
        top.addWidget(self.filter)
        top.addStretch(1)
        lay.addLayout(top)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Categoria", "Objeto", "Indicador", "Média",
                                              "Desvio padrão", "IC 95% (±)", "Mín – Máx"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        b_csv = QPushButton("Exportar CSV…")
        b_copy = QPushButton("Copiar")
        btns.addButton(b_csv, QDialogButtonBox.ActionRole)
        btns.addButton(b_copy, QDialogButtonBox.ActionRole)
        b_csv.clicked.connect(self._export)
        b_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(
            self.result.to_csv().replace(";", "\t")))
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._fill()

    def _fill(self, *_):
        cat = self.filter.currentText()
        rows = [r for r in self.rows if cat in ("Todas", "") or r.category == cat]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r.category, r.obj, r.metric, _fmt(r.mean), _fmt(r.stdev), _fmt(r.half_width),
                    f"{_fmt(min(r.values))} – {_fmt(max(r.values))}" if r.values else "—"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j >= 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if r.metric.startswith("Utilização") and r.mean > 85:
                    it.setBackground(QBrush(QColor("#ffe2cc")))
                self.table.setItem(i, j, it)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar resultados",
                                              f"{self.result.model_name}_resultados.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(self.result.to_csv())


LEGEND = [
    (EK.ENTITY, "Entidade", "Item processado pelo sistema (peça, cliente, documento). "
                            "Sem fluxo de entrada é uma fonte de chegadas."),
    (EK.FUNCTION, "Função", "Local onde a entidade sofre uma ação (processamento, montagem, "
                            "inspeção, espera)."),
    (CK.FLOW, "Fluxo da entidade", "Direção do movimento da entidade entre elementos. "
                                   "O traço na origem marca a entrada no sistema."),
    (EK.RESOURCE, "Recurso", "Elemento usado para executar a função (máquina, operador). "
                             "É ligado à função por uma seta dupla."),
    (EK.CONTROL, "Controle", "Regra que governa a função (plano, ordem, política). "
                             "É ligado à função por seta tracejada."),
    (EK.RULE_AND, "Regra E (&)", "Fluxos paralelos: divide a entidade em todos os ramos ou "
                                 "junta uma entidade de cada ramo."),
    (EK.RULE_OR, "Regra OU (X)", "Fluxos alternativos: apenas um dos caminhos é seguido."),
    (EK.RULE_ANDOR, "Regra E/OU (O)", "Combinação: um ou mais caminhos podem ser seguidos."),
    (EK.MOVEMENT, "Movimentação", "Deslocamento da entidade entre funções (transporte)."),
    (EK.NOTE, "Informação explicativa", "Texto de apoio para esclarecer o modelo."),
    (EK.EXIT, "Ponto final do sistema", "Local onde a entidade deixa o sistema modelado."),
    (EK.CONNECTOR, "Conexão com outra figura", "Liga partes do diagrama (ou outras páginas); "
                                               "conectores com o mesmo nome estão ligados."),
]


class LegendDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notação IDEF-SIM")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Símbolos da técnica IDEF-SIM (Leal, Almeida e Montevechi, 2008) "
                             "e a forma como o IDEF-SIM Studio os interpreta na simulação."))
        t = QTableWidget(len(LEGEND), 3)
        t.setHorizontalHeaderLabels(["Símbolo", "Elemento", "Significado"])
        t.setIconSize(QSize(40, 40))
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setWordWrap(True)
        for i, (k, name, desc) in enumerate(LEGEND):
            icon = shapes.connection_icon(k, 40) if isinstance(k, CK) else shapes.element_icon(k, 40)
            it = QTableWidgetItem()
            it.setIcon(icon)
            t.setItem(i, 0, it)
            t.setItem(i, 1, QTableWidgetItem(name))
            t.setItem(i, 2, QTableWidgetItem(desc))
            t.setRowHeight(i, 52)
        t.setColumnWidth(0, 60)
        t.setColumnWidth(1, 170)
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
