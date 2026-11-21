"""Testes da interface (executados em modo offscreen)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from idefsim.examples import montagem  # noqa: E402
from idefsim.gui.main_window import MainWindow  # noqa: E402
from idefsim.model import ConnectionKind as CK, ElementKind as EK  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _click(win, scene_pos):
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, win.view.mapFromScene(scene_pos))


def test_draw_with_mouse(app):
    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    win.view.resetTransform()
    win.view.centerOn(300, 0)
    sc = win.scene
    for kind, x in ((EK.ENTITY, 100), (EK.FUNCTION, 300), (EK.EXIT, 500)):
        sc.set_tool("add", kind)
        _click(win, QPoint(x, 0))
    m = sc.model
    assert len(m.elements) == 3
    ids = {e.kind: e.id for e in m.elements.values()}
    sc.set_tool("link", CK.FLOW)
    for a, b in ((100, 300), (300, 500)):
        _click(win, QPoint(a, 0))
        _click(win, QPoint(b, 0))
    assert len(m.connections) == 2
    assert m.outgoing(ids[EK.ENTITY])[0].target == ids[EK.FUNCTION]
    n_hist = len(win.history)
    win.undo()
    assert len(win.scene.model.connections) == 1
    win.redo()
    assert len(win.scene.model.connections) == 2
    assert len(win.history) == n_hist
    win.dirty = False
    win.close()


def test_load_example_and_export(app, tmp_path):
    win = MainWindow()
    win._set_model(montagem(), None)
    assert win.svg_bytes().startswith(b"<?xml")
    assert not win.image().isNull()
    win.close()


def test_arrowhead_visible_when_rule_touches_function(app):
    from idefsim.model import Model
    m = Model()
    f = m.add_element(EK.FUNCTION, 0, 0)
    r = m.add_element(EK.RULE_OR, 80, 0)   # regra sobreposta à função
    m.add_connection(CK.FLOW, f.id, r.id)
    win = MainWindow()
    win._set_model(m, None)
    ed = next(iter(win.scene.edges.values()))
    a, b = ed.points
    assert b.x() - a.x() >= 14 and ed.zValue() > win.scene.nodes[f.id].zValue()
    win.dirty = False
    win.close()


def test_change_flow_to_entry(app):
    from idefsim.model import Model
    m = Model()
    e = m.add_element(EK.ENTITY, 0, 0)
    f = m.add_element(EK.FUNCTION, 200, 0)
    c = m.add_connection(CK.FLOW, e.id, f.id)
    win = MainWindow()
    win._set_model(m, None)
    assert win.scene.set_connection_kind(c.id, CK.ENTRY)
    assert win.scene.model.connections[c.id].kind == CK.ENTRY
    win.undo()
    assert next(iter(win.scene.model.connections.values())).kind == CK.FLOW
    win.dirty = False
    win.close()
