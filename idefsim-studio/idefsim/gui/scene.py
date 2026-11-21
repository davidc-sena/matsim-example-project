"""Cena do diagrama: ferramentas de inserção, ligação, seleção e remoção."""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from ..model import ConnectionError_, ConnectionKind as CK, ElementKind as EK, Model
from .items import GRID, EdgeItem, NodeItem


class DiagramScene(QGraphicsScene):
    modelChanged = Signal(str, str)   # descrição, chave de agrupamento
    message = Signal(str)
    toolFinished = Signal()

    def __init__(self, model: Model, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 6000, 5000)
        self.model = model
        self.nodes: dict[str, NodeItem] = {}
        self.edges: dict[str, EdgeItem] = {}
        self.tool: str = "select"
        self.tool_kind = None
        self._link_src: NodeItem | None = None
        self._temp: QGraphicsLineItem | None = None
        self._press_pos: dict[str, QPointF] = {}
        self.show_grid = True
        self.rebuild()

    # ---------------------------------------------------------------- modelo
    def set_model(self, model: Model) -> None:
        self.model = model
        self.rebuild()

    def rebuild(self) -> None:
        self.cancel_link()
        self.clear()
        self.nodes.clear()
        self.edges.clear()
        for e in self.model.elements.values():
            self._add_node_item(e)
        for c in self.model.connections.values():
            self._add_edge_item(c)

    def _add_node_item(self, e) -> NodeItem:
        it = NodeItem(e)
        self.addItem(it)
        self.nodes[e.id] = it
        return it

    def _add_edge_item(self, c) -> EdgeItem:
        it = EdgeItem(c, self.nodes[c.source], self.nodes[c.target], self.model)
        self.addItem(it)
        self.edges[c.id] = it
        return it

    def refresh_all(self) -> None:
        for n in self.nodes.values():
            n.refresh()
        for ed in self.edges.values():
            ed.adjust()

    def refresh_element(self, eid: str) -> None:
        if eid in self.nodes:
            self.nodes[eid].refresh()
        for ed in self.edges.values():
            ed.update()

    # ------------------------------------------------------------ ferramentas
    def set_tool(self, tool: str, kind=None) -> None:
        self.cancel_link()
        self.tool, self.tool_kind = tool, kind
        for v in self.views():
            v.viewport().setCursor(Qt.ArrowCursor if tool == "select" else Qt.CrossCursor)
            v.setDragMode(v.DragMode.RubberBandDrag if tool == "select" else v.DragMode.NoDrag)

    def cancel_link(self) -> None:
        if self._temp is not None:
            self.removeItem(self._temp)
        self._temp = None
        self._link_src = None

    def _node_at(self, pos: QPointF) -> NodeItem | None:
        for it in self.items(pos):
            if isinstance(it, NodeItem):
                return it
        return None

    def add_element(self, kind: EK, pos: QPointF):
        x, y = round(pos.x() / GRID) * GRID, round(pos.y() / GRID) * GRID
        e = self.model.add_element(kind, x, y)
        self.clearSelection()
        it = self._add_node_item(e)
        it.setSelected(True)
        self.modelChanged.emit(f"Inserir {e.name}", "")
        return e

    def add_connection(self, kind: CK, src: str, dst: str):
        try:
            c = self.model.add_connection(kind, src, dst)
        except ConnectionError_ as ex:
            self.message.emit(str(ex))
            return None
        if kind == CK.FLOW:
            outs = self.model.outgoing(c.source)
            if len(outs) > 1:  # distribui probabilidades igualmente
                for o in outs:
                    o.probability = round(1 / len(outs), 4)
        self._add_edge_item(c)
        self.refresh_all()
        self.clearSelection()
        self.edges[c.id].setSelected(True)
        self.modelChanged.emit("Conectar elementos", "")
        return c

    def set_entry_arrow(self, eid: str, pos: QPointF | None = None) -> bool:
        """Coloca o fluxo de entrada no sistema na entidade, do lado mais próximo de ``pos``."""
        e = self.model.elements[eid]
        if e.kind != EK.ENTITY:
            self.message.emit("O fluxo de entrada no sistema é colocado sobre uma Entidade.")
            return False
        side = e.params.get("arrival_side", "left")
        if pos is not None:
            dx, dy = pos.x() - e.x, pos.y() - e.y
            if abs(dx) >= abs(dy):
                side = "left" if dx <= 0 else "right"
            else:
                side = "top" if dy < 0 else "bottom"
        e.params["external_arrival"] = True
        e.params["arrival_side"] = side
        self.nodes[eid].refresh()
        self.modelChanged.emit("Fluxo de entrada no sistema", "")
        return True

    def delete_selected(self) -> None:
        sel = self.selectedItems()
        if not sel:
            return
        for it in sel:
            if isinstance(it, EdgeItem):
                self.model.connections.pop(it.conn.id, None)
            elif isinstance(it, NodeItem):
                self.model.remove_element(it.element.id)
        self.rebuild()
        self.modelChanged.emit("Remover", "")

    def duplicate_selected(self) -> None:
        sel = [it for it in self.selectedItems() if isinstance(it, NodeItem)]
        if not sel:
            return
        self.clearSelection()
        for it in sel:
            src = it.element
            e = self.model.add_element(src.kind, src.x + 30, src.y + 30, **src.params)
            e.description = src.description
            if src.kind not in (EK.RULE_AND, EK.RULE_OR, EK.RULE_ANDOR, EK.CONNECTOR):
                e.name = f"{src.name} (cópia)"
            self._add_node_item(e).setSelected(True)
        self.modelChanged.emit("Duplicar", "")

    def select_element(self, eid: str | None) -> None:
        if eid and eid in self.nodes:
            self.clearSelection()
            self.nodes[eid].setSelected(True)
            for v in self.views():
                v.centerOn(self.nodes[eid])

    # ----------------------------------------------------------------- mouse
    def mousePressEvent(self, ev):
        if ev.button() == Qt.RightButton and self.tool != "select":
            self.set_tool("select")
            self.toolFinished.emit()
            return
        if ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        pos = ev.scenePos()
        if self.tool == "add":
            self.add_element(self.tool_kind, pos)
            if not ev.modifiers() & Qt.ShiftModifier:
                self.set_tool("select")
                self.toolFinished.emit()
            return
        if self.tool == "entry":
            node = self._node_at(pos)
            if node is None or node.element.kind != EK.ENTITY:
                self.message.emit("Clique sobre uma Entidade, do lado de onde ela chega ao sistema.")
                return
            self.set_entry_arrow(node.element.id, pos)
            if not ev.modifiers() & Qt.ShiftModifier:
                self.set_tool("select")
                self.toolFinished.emit()
            return
        if self.tool == "link":
            node = self._node_at(pos)
            if node is None:
                self.cancel_link()
                return
            if self._link_src is None:
                self._link_src = node
                self._temp = QGraphicsLineItem(QLineF(node.scenePos(), pos))
                self._temp.setPen(QPen(QColor("#1a73e8"), 1.5, Qt.DashLine))
                self._temp.setZValue(10)
                self.addItem(self._temp)
                self.message.emit(f"Origem: {node.element.name}. Clique no destino (Esc cancela).")
            else:
                src = self._link_src
                self.cancel_link()
                self.add_connection(self.tool_kind, src.element.id, node.element.id)
                if ev.modifiers() & Qt.ShiftModifier:
                    return
            return
        super().mousePressEvent(ev)
        self._press_pos = {it.element.id: it.pos() for it in self.selectedItems()
                           if isinstance(it, NodeItem)}

    def mouseMoveEvent(self, ev):
        if self._temp is not None and self._link_src is not None:
            self._temp.setLine(QLineF(self._link_src.scenePos(), ev.scenePos()))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if self._press_pos:
            moved = any(eid in self.nodes and self.nodes[eid].pos() != p
                        for eid, p in self._press_pos.items())
            self._press_pos = {}
            if moved:
                self.modelChanged.emit("Mover", "")

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.cancel_link()
            if self.tool != "select":
                self.set_tool("select")
                self.toolFinished.emit()
            return
        super().keyPressEvent(ev)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#ffffff"))
        if not self.show_grid:
            return
        step = GRID * 2
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        painter.setPen(QPen(QColor("#e9edf2"), 0))
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += step
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += step
