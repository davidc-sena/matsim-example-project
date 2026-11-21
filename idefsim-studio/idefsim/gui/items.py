"""Itens gráficos do diagrama."""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
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
            for ed in self.edges:
                ed.adjust()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsItem):
    def __init__(self, conn: Connection, src: NodeItem, dst: NodeItem, model):
        super().__init__()
        self.conn, self.src, self.dst, self.model = conn, src, dst, model
        src.edges.append(self)
        dst.edges.append(self)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        self.a = QPointF()
        self.b = QPointF()
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

    def adjust(self) -> None:
        self.prepareGeometryChange()
        self.a = self.src.boundary_point(self.dst.scenePos())
        self.b = self.dst.boundary_point(self.src.scenePos())
        self.update()

    def is_entry(self) -> bool:
        s = self.model.elements.get(self.conn.source)
        return (self.conn.kind == CK.FLOW and s is not None and s.kind == EK.ENTITY
                and not self.model.incoming(s.id))

    def boundingRect(self) -> QRectF:
        return QRectF(self.a, self.b).normalized().adjusted(-60, -20, 60, 20)

    def shape(self) -> QPainterPath:
        p = QPainterPath(self.a)
        p.lineTo(self.b)
        st = QPainterPathStroker()
        st.setWidth(10)
        return st.createStroke(p)

    def paint(self, painter, option, widget=None):
        if QLineF(self.a, self.b).length() < 2:
            return
        color = shapes.SELECT if self.isSelected() else shapes.INK
        shapes.draw_link(painter, self.conn.kind, self.a, self.b, color, entry=self.is_entry())
        txt = self.label_text()
        if txt:
            mid = (self.a + self.b) / 2
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
