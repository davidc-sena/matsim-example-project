"""Itens gráficos do diagrama."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..model import (Connection, ConnectionKind as CK, Element, ElementKind as EK,
                     PROCESS_KINDS, RULE_KINDS)
from . import shapes

GRID = 10


class NodeItem(QGraphicsItem):
    def __init__(self, element: Element):
        super().__init__()
        self.element = element
        self.edges: list[EdgeItem] = []
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setPos(element.x, element.y)
        self.setZValue(1 if element.kind != EK.NOTE else 0.5)
        self._rect = shapes.node_rect(element.kind)
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        e = self.element
        from ..model import KIND_LABELS
        lines = [f"<b>{KIND_LABELS[e.kind]}</b>: {e.name}"]
        lines += [f"{k}: {v}" for k, v in e.params.items()]
        if e.description:
            lines.append(f"<i>{e.description}</i>")
        return "<br>".join(lines)

    def refresh(self) -> None:
        self.prepareGeometryChange()
        self.setToolTip(self._tooltip())
        self.update()
        for ed in self.edges:
            ed.adjust()

    def boundingRect(self) -> QRectF:
        r = self._rect.adjusted(-3, -3, 3, 3)
        if self.element.kind == EK.EXIT:
            r = r.adjusted(-40, 0, 40, 34)
        return r

    def shape(self) -> QPainterPath:
        return shapes.node_path(self.element.kind, self._rect)

    def paint(self, painter, option, widget=None):
        shapes.paint_node(painter, self.element.kind, self._rect, self.element.name,
                          self.isSelected())

    def body_rect(self) -> QRectF:
        """Retângulo útil do símbolo em coordenadas de cena (corpo da seta na movimentação)."""
        r = self._rect
        if self.element.kind == EK.MOVEMENT:
            head = min(28.0, r.width() * 0.25)
            r = r.adjusted(0, r.height() * 0.22, -head, -r.height() * 0.22)
        return r.translated(self.scenePos())

    def boundary_point(self, toward: QPointF) -> QPointF:
        c = self.scenePos()
        dx, dy = toward.x() - c.x(), toward.y() - c.y()
        if dx == 0 and dy == 0:
            return c
        if self.element.kind in shapes.CIRCULAR:
            rad = self._rect.width() / 2
            d = math.hypot(dx, dy)
            return QPointF(c.x() + dx / d * rad, c.y() + dy / d * rad)
        hw, hh = self._rect.width() / 2, self._rect.height() / 2
        if self.element.kind == EK.MOVEMENT:  # corpo da seta é mais estreito
            hh -= self._rect.height() * 0.22
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
        return QPointF(c.x() + dx * t, c.y() + dy * t)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            v = QPointF(value)
            return QPointF(round(v.x() / GRID) * GRID, round(v.y() / GRID) * GRID)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.element.x, self.element.y = self.pos().x(), self.pos().y()
            todo = set(self.edges)
            for ed in self.edges:  # a ordem dos encaixes na face da função pode mudar
                if ed.conn.kind in SIDE_KINDS:
                    todo.update(e for e in ed.dst.edges if e.conn.kind == ed.conn.kind)
            for ed in todo:
                ed.adjust()
        return super().itemChange(change, value)


SIDE_KINDS = (CK.RESOURCE, CK.CONTROL)
_GAP = 18  # afastamento mínimo das rotas ortogonais


def _route_from_below(src: QRectF, body: QRectF, tx: float) -> list[QPointF]:
    """Rota ortogonal de um rótulo até à face inferior de ``body`` (no ponto tx)."""
    t = QPointF(tx, body.bottom())
    sx = src.center().x()
    if src.top() >= body.bottom() + 4:            # caso normal: rótulo abaixo
        s = QPointF(sx, src.top())
        if abs(sx - tx) < 1:
            return [s, t]
        ym = (s.y() + t.y()) / 2
        return [s, QPointF(sx, ym), QPointF(tx, ym), t]
    ylow = max(body.bottom(), src.bottom()) + _GAP
    s = QPointF(sx, src.bottom())
    if src.bottom() + _GAP < body.top():          # rótulo acima: contorna a função
        x_out = body.left() - _GAP if sx < body.center().x() else body.right() + _GAP
        y1 = s.y() + _GAP / 2
        return [s, QPointF(sx, y1), QPointF(x_out, y1), QPointF(x_out, ylow),
                QPointF(tx, ylow), t]
    return [s, QPointF(sx, ylow), QPointF(tx, ylow), t]   # rótulo ao lado


def _flip(r: QRectF) -> QRectF:
    return QRectF(r.left(), -r.bottom(), r.width(), r.height())


class EdgeItem(QGraphicsItem):
    def __init__(self, conn: Connection, src: NodeItem, dst: NodeItem, model):
        super().__init__()
        self.conn, self.src, self.dst, self.model = conn, src, dst, model
        src.edges.append(self)
        dst.edges.append(self)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        self.points: list[QPointF] = [QPointF(), QPointF()]
        self.adjust()

    def detach(self) -> None:
        for n in (self.src, self.dst):
            if self in n.edges:
                n.edges.remove(self)

    def label_text(self) -> str:
        c = self.conn
        parts = [c.label] if c.label else []
        if c.kind == CK.FLOW:
            src = self.model.elements[c.source]
            n_out = len(self.model.outgoing(src.id))
            if (src.kind in (EK.RULE_OR, EK.RULE_ANDOR) or
                    (src.kind in PROCESS_KINDS and n_out > 1)) and n_out > 0:
                parts.append(f"{c.probability * 100:g}%")
        return "  ".join(parts)

    def _slot_x(self, body: QRectF) -> float:
        """Distribui várias ligações do mesmo tipo ao longo da face da função."""
        sibs = sorted((e for e in self.dst.edges if e.conn.kind == self.conn.kind),
                      key=lambda e: (e.src.scenePos().x(), e.conn.id))
        if len(sibs) <= 1:  # uma só ligação: seta reta se o rótulo estiver alinhado
            sx = self.src.body_rect().center().x()
            return min(max(sx, body.left() + 12), body.right() - 12)
        i = sibs.index(self) if self in sibs else 0
        return body.left() + body.width() * (i + 1) / (len(sibs) + 1)

    def adjust(self) -> None:
        self.prepareGeometryChange()
        if self.conn.kind in SIDE_KINDS:
            body, src = self.dst.body_rect(), self.src.body_rect()
            tx = self._slot_x(body)
            if self.conn.kind == CK.RESOURCE:     # recurso: entra por baixo
                pts = _route_from_below(src, body, tx)
            else:                                 # controle: entra por cima (espelhado)
                pts = [QPointF(p.x(), -p.y()) for p in
                       _route_from_below(_flip(src), _flip(body), tx)]
            self.points = pts
        else:
            self.points = [self.src.boundary_point(self.dst.scenePos()),
                           self.dst.boundary_point(self.src.scenePos())]
        self.update()

    def is_entry(self) -> bool:
        s = self.model.elements.get(self.conn.source)
        return (self.conn.kind == CK.FLOW and s is not None and s.kind == EK.ENTITY
                and not self.model.incoming(s.id))

    def _path(self) -> QPainterPath:
        p = QPainterPath(self.points[0])
        for pt in self.points[1:]:
            p.lineTo(pt)
        return p

    def boundingRect(self) -> QRectF:
        return self._path().boundingRect().adjusted(-60, -20, 60, 20)

    def shape(self) -> QPainterPath:
        st = QPainterPathStroker()
        st.setWidth(10)
        return st.createStroke(self._path())

    def paint(self, painter, option, widget=None):
        if self._path().length() < 2:
            return
        color = shapes.SELECT if self.isSelected() else shapes.INK
        shapes.draw_link(painter, self.conn.kind, self.points, color, entry=self.is_entry())
        txt = self.label_text()
        if txt:
            k = len(self.points) // 2
            mid = (self.points[k - 1] + self.points[k]) / 2
            f = QFont(painter.font())
            f.setPointSizeF(8)
            painter.setFont(f)
            r = painter.boundingRect(QRectF(mid.x() - 60, mid.y() - 18, 120, 14),
                                     Qt.AlignCenter, txt)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawRect(r.adjusted(-2, 0, 2, 0))
            painter.setPen(QPen(color))
            painter.drawText(r, Qt.AlignCenter, txt)
