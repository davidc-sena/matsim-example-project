"""Desenho dos símbolos IDEF-SIM (partilhado entre o diagrama e os ícones)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from ..model import ConnectionKind as CK, ElementKind as EK

SIZES: dict[EK, tuple[float, float]] = {
    EK.ENTITY: (64, 64),
    EK.FUNCTION: (130, 64),
    EK.RESOURCE: (120, 30),
    EK.CONTROL: (120, 30),
    EK.MOVEMENT: (130, 56),
    EK.RULE_AND: (38, 38),
    EK.RULE_OR: (38, 38),
    EK.RULE_ANDOR: (38, 38),
    EK.EXIT: (40, 40),
    EK.CONNECTOR: (36, 36),
    EK.NOTE: (150, 56),
}

FILL = {
    EK.ENTITY: QColor("#fff6d6"),
    EK.FUNCTION: QColor("#e3eefc"),
    EK.MOVEMENT: QColor("#e5f5e3"),
    EK.NOTE: QColor("#fffbe8"),
}
INK = QColor("#1d1d1f")
SELECT = QColor("#1a73e8")
RULE_SYMBOL = {EK.RULE_AND: "&", EK.RULE_OR: "X", EK.RULE_ANDOR: "O"}
CIRCULAR = {EK.ENTITY, EK.EXIT, EK.CONNECTOR}


def node_rect(kind: EK) -> QRectF:
    w, h = SIZES[kind]
    return QRectF(-w / 2, -h / 2, w, h)


def movement_polygon(r: QRectF) -> QPolygonF:
    head = min(28.0, r.width() * 0.25)
    body = r.height() * 0.22
    cy = r.center().y()
    return QPolygonF([
        QPointF(r.left(), r.top() + body), QPointF(r.right() - head, r.top() + body),
        QPointF(r.right() - head, r.top()), QPointF(r.right(), cy),
        QPointF(r.right() - head, r.bottom()), QPointF(r.right() - head, r.bottom() - body),
        QPointF(r.left(), r.bottom() - body)])


def node_path(kind: EK, r: QRectF) -> QPainterPath:
    p = QPainterPath()
    if kind in CIRCULAR:
        p.addEllipse(r)
    elif kind == EK.MOVEMENT:
        p.addPolygon(movement_polygon(r))
        p.closeSubpath()
    else:
        p.addRect(r)
    return p


def _fit_font(painter: QPainter, text: str, rect: QRectF, base: float = 9.0, bold=False) -> None:
    f = QFont(painter.font())
    f.setPointSizeF(base)
    f.setBold(bold)
    painter.setFont(f)
    flags = Qt.AlignCenter | Qt.TextWordWrap
    while base > 6 and painter.boundingRect(rect, flags, text).height() > rect.height():
        base -= 0.5
        f.setPointSizeF(base)
        painter.setFont(f)


def paint_node(p: QPainter, kind: EK, r: QRectF, name: str, selected: bool = False,
               show_name: bool = True) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(SELECT if selected else INK, 2.2 if selected else 1.4)
    p.setPen(pen)
    p.setBrush(QBrush(FILL.get(kind, QColor("white"))))
    text_rect = r.adjusted(4, 2, -4, -2)

    if kind == EK.ENTITY:
        p.drawEllipse(r)
    elif kind == EK.FUNCTION:
        p.drawRect(r)
    elif kind == EK.MOVEMENT:
        p.drawPolygon(movement_polygon(r))
        head = min(28.0, r.width() * 0.25)
        text_rect = r.adjusted(4, r.height() * 0.22, -head, -r.height() * 0.22)
    elif kind in RULE_SYMBOL:
        p.drawRect(r)
        f = QFont(p.font())
        f.setPointSizeF(max(8.0, r.height() * 0.42))
        f.setBold(True)
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, RULE_SYMBOL[kind])
        return
    elif kind == EK.EXIT:
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(r)
        p.setBrush(QBrush(INK if not selected else SELECT))
        p.drawEllipse(r.center(), r.width() * 0.28, r.height() * 0.28)
        if show_name:
            p.setPen(QPen(INK))
            _fit_font(p, name, QRectF(r.left() - 40, r.bottom() + 2, r.width() + 80, 30))
            p.drawText(QRectF(r.left() - 40, r.bottom() + 2, r.width() + 80, 30),
                       Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, name)
        return
    elif kind == EK.CONNECTOR:
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(r)
        _fit_font(p, name, r.adjusted(3, 3, -3, -3), 10, bold=True)
        p.drawText(r, Qt.AlignCenter, name if show_name else "A")
        return
    elif kind == EK.NOTE:
        fold = 12
        poly = QPolygonF([r.topLeft(), QPointF(r.right() - fold, r.top()),
                          QPointF(r.right(), r.top() + fold), r.bottomRight(), r.bottomLeft()])
        p.setPen(QPen(SELECT if selected else INK, pen.widthF(), Qt.DashLine))
        p.drawPolygon(poly)
        p.drawLine(QPointF(r.right() - fold, r.top()), QPointF(r.right() - fold, r.top() + fold))
        p.drawLine(QPointF(r.right() - fold, r.top() + fold), QPointF(r.right(), r.top() + fold))
        p.setPen(QPen(INK))
        f = QFont(p.font())
        f.setItalic(True)
        p.setFont(f)
    elif kind in (EK.RESOURCE, EK.CONTROL):
        # Rótulo sublinhado; o símbolo propriamente dito é a seta de ligação.
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 230)))
        p.drawRect(r)
        p.setPen(QPen(SELECT if selected else INK, 1.2,
                      Qt.SolidLine if kind == EK.RESOURCE else Qt.DashLine))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        icon = QRectF(r.left(), r.top(), 16, r.height())
        cx = icon.center().x()
        if kind == EK.RESOURCE:  # seta dupla vertical
            p.drawLine(QPointF(cx, r.top() + 4), QPointF(cx, r.bottom() - 4))
            for y, d in ((r.top() + 4, 1), (r.bottom() - 4, -1)):
                p.drawLine(QPointF(cx, y), QPointF(cx - 4, y + 5 * d))
                p.drawLine(QPointF(cx, y), QPointF(cx + 4, y + 5 * d))
        else:  # seta tracejada para baixo
            p.drawLine(QPointF(cx, r.top() + 4), QPointF(cx, r.bottom() - 4))
            p.drawLine(QPointF(cx, r.bottom() - 4), QPointF(cx - 4, r.bottom() - 9))
            p.drawLine(QPointF(cx, r.bottom() - 4), QPointF(cx + 4, r.bottom() - 9))
        text_rect = r.adjusted(18, 0, -2, 0)
        p.setPen(QPen(INK))

    if show_name:
        p.setPen(QPen(INK))
        _fit_font(p, name, text_rect, bold=kind in (EK.RESOURCE,))
        p.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, name)


def element_icon(kind: EK, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    w, h = SIZES[kind]
    s = (size - 4) / max(w, h)
    if kind in (EK.RESOURCE, EK.CONTROL):
        s = (size - 4) / 40
        w = 40
    p.translate(size / 2, size / 2)
    p.scale(s, s)
    r = QRectF(-w / 2, -h / 2, w, h)
    paint_node(p, kind, r, "", show_name=kind == EK.CONNECTOR)
    p.end()
    return QIcon(pm)


def connection_icon(kind: CK, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    a, b = QPointF(4, size - 6), QPointF(size - 5, 6)
    draw_link(p, kind, a, b, scale=0.8)
    p.end()
    return QIcon(pm)


def _arrow_head(p: QPainter, tip: QPointF, frm: QPointF, size: float) -> None:
    import math
    ang = math.atan2(tip.y() - frm.y(), tip.x() - frm.x())
    pts = [tip]
    for da in (2.65, -2.65):
        pts.append(QPointF(tip.x() + size * math.cos(ang + da), tip.y() + size * math.sin(ang + da)))
    old = p.brush()
    p.setBrush(QBrush(p.pen().color()))
    p.drawPolygon(QPolygonF(pts))
    p.setBrush(old)


LINK_STYLE = {
    CK.FLOW: (Qt.SolidLine, 1.6),
    CK.RESOURCE: (Qt.SolidLine, 1.2),
    CK.CONTROL: (Qt.DashLine, 1.2),
    CK.NOTE: (Qt.DotLine, 1.0),
}


def draw_link(p: QPainter, kind: CK, a: QPointF, b: QPointF, color: QColor = INK,
              scale: float = 1.0, entry: bool = False) -> None:
    style, width = LINK_STYLE[kind]
    p.setPen(QPen(color, width, style, Qt.RoundCap))
    p.drawLine(a, b)
    p.setPen(QPen(color, width, Qt.SolidLine))
    hs = 10 * scale
    if kind in (CK.FLOW, CK.CONTROL):
        _arrow_head(p, b, a, hs)
    elif kind == CK.RESOURCE:
        _arrow_head(p, b, a, hs)
        _arrow_head(p, a, b, hs)
    if entry:  # fluxo de entrada no sistema: traço perpendicular na origem
        import math
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        d = QPointF(-math.sin(ang) * 7, math.cos(ang) * 7)
        m = QPointF(a.x() + math.cos(ang) * 10, a.y() + math.sin(ang) * 10)
        p.drawLine(m - d, m + d)
