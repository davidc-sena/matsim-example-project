"""Modelos de exemplo."""
from __future__ import annotations

from .model import ConnectionKind as CK, ElementKind as EK, Model


def usinagem_inspecao() -> Model:
    """Célula de usinagem com inspeção e retrabalho (10% de rejeição)."""
    m = Model(name="Célula de usinagem com inspeção", author="IDEF-SIM Studio",
              description="Peças chegam, são usinadas no torno, transportadas até a "
                          "inspeção; 10% seguem para retrabalho e voltam à inspeção.")
    m.settings.duration, m.settings.warmup, m.settings.replications = 480, 60, 10
    peca = m.add_element(EK.ENTITY, 60, 200, "Peça", interarrival="EXPO(6)")
    usin = m.add_element(EK.FUNCTION, 220, 200, "Usinar", duration="TRIA(3, 4.5, 6)")
    torno = m.add_element(EK.RESOURCE, 220, 320, "Torno", capacity=1)
    ctrl = m.add_element(EK.CONTROL, 220, 80, "Plano de produção")
    mov = m.add_element(EK.MOVEMENT, 400, 200, "Transportar", duration="UNIF(1, 2)")
    oper = m.add_element(EK.RESOURCE, 400, 320, "Operador logístico", capacity=1)
    insp = m.add_element(EK.FUNCTION, 580, 200, "Inspecionar", duration="NORM(4; 0,5)")
    inspetor = m.add_element(EK.RESOURCE, 580, 320, "Inspetor", capacity=1)
    regra = m.add_element(EK.RULE_OR, 720, 200)
    fim = m.add_element(EK.EXIT, 860, 200, "Expedição")
    retr = m.add_element(EK.FUNCTION, 720, 420, "Retrabalhar", duration="EXPO(8)")
    nota = m.add_element(EK.NOTE, 880, 80, "Taxa de rejeição histórica: 10%")
    m.add_connection(CK.FLOW, peca.id, usin.id)
    m.add_connection(CK.FLOW, usin.id, mov.id)
    m.add_connection(CK.FLOW, mov.id, insp.id)
    m.add_connection(CK.FLOW, insp.id, regra.id)
    m.add_connection(CK.FLOW, regra.id, fim.id, probability=0.9)
    m.add_connection(CK.FLOW, regra.id, retr.id, probability=0.1)
    m.add_connection(CK.FLOW, retr.id, insp.id)
    m.add_connection(CK.RESOURCE, torno.id, usin.id)
    m.add_connection(CK.RESOURCE, oper.id, mov.id)
    m.add_connection(CK.RESOURCE, inspetor.id, insp.id)
    m.add_connection(CK.CONTROL, ctrl.id, usin.id)
    m.add_connection(CK.NOTE, nota.id, regra.id)
    return m


def montagem() -> Model:
    """Montagem: base e tampa se juntam em uma regra E (&) e formam o produto."""
    m = Model(name="Montagem com junção E", author="IDEF-SIM Studio")
    m.settings.duration, m.settings.replications = 600, 5
    base = m.add_element(EK.ENTITY, 60, 120, "Base", interarrival="EXPO(5)")
    tampa = m.add_element(EK.ENTITY, 60, 300, "Tampa", interarrival="EXPO(5)")
    pb = m.add_element(EK.FUNCTION, 220, 120, "Preparar base", duration="TRIA(2, 3, 4)")
    pt = m.add_element(EK.FUNCTION, 220, 300, "Preparar tampa", duration="TRIA(1, 2, 3)")
    j = m.add_element(EK.RULE_AND, 380, 210)
    prod = m.add_element(EK.ENTITY, 480, 210, "Produto")
    mont = m.add_element(EK.FUNCTION, 620, 210, "Montar", duration="NORM(3.5, 0.4)")
    mont_r = m.add_element(EK.RESOURCE, 620, 330, "Montador", capacity=1)
    fim = m.add_element(EK.EXIT, 780, 210, "Armazém")
    for a, b in ((base, pb), (tampa, pt), (pb, j), (pt, j), (j, prod), (prod, mont), (mont, fim)):
        m.add_connection(CK.FLOW, a.id, b.id)
    m.add_connection(CK.RESOURCE, mont_r.id, mont.id)
    return m


ALL = {"Célula de usinagem com inspeção": usinagem_inspecao,
       "Montagem com junção E": montagem}
