"""Modelo de dados (independente da interface gráfica) para diagramas IDEF-SIM.

Notação IDEF-SIM (Leal, Almeida & Montevechi, 2008), elementos suportados:

* Entidade ............................ círculo
* Função .............................. retângulo
* Recurso ............................. ligado à função por seta dupla
* Controle ............................ ligado à função por seta tracejada
* Movimentação ........................ seta larga (bloco)
* Regras de fluxo: E (&), OU (X), E/OU (O)
* Ponto final do sistema
* Conexão com outra figura (conector)
* Informação explicativa (nota)
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from enum import Enum


class ElementKind(str, Enum):
    ENTITY = "entity"
    FUNCTION = "function"
    RESOURCE = "resource"
    CONTROL = "control"
    MOVEMENT = "movement"
    RULE_AND = "rule_and"
    RULE_OR = "rule_or"
    RULE_ANDOR = "rule_andor"
    EXIT = "exit"
    CONNECTOR = "connector"
    NOTE = "note"


class ConnectionKind(str, Enum):
    FLOW = "flow"          # fluxo da entidade
    RESOURCE = "resource"  # ligação recurso <-> função
    CONTROL = "control"    # controle -> função
    NOTE = "note"          # informação explicativa


KIND_LABELS: dict[ElementKind, str] = {
    ElementKind.ENTITY: "Entidade",
    ElementKind.FUNCTION: "Função",
    ElementKind.RESOURCE: "Recurso",
    ElementKind.CONTROL: "Controle",
    ElementKind.MOVEMENT: "Movimentação",
    ElementKind.RULE_AND: "Regra E (&)",
    ElementKind.RULE_OR: "Regra OU (X)",
    ElementKind.RULE_ANDOR: "Regra E/OU (O)",
    ElementKind.EXIT: "Ponto final",
    ElementKind.CONNECTOR: "Conexão",
    ElementKind.NOTE: "Informação explicativa",
}

CONNECTION_LABELS: dict[ConnectionKind, str] = {
    ConnectionKind.FLOW: "Fluxo da entidade",
    ConnectionKind.RESOURCE: "Ligação de recurso",
    ConnectionKind.CONTROL: "Ligação de controle",
    ConnectionKind.NOTE: "Ligação de nota",
}

RULE_KINDS = {ElementKind.RULE_AND, ElementKind.RULE_OR, ElementKind.RULE_ANDOR}
PROCESS_KINDS = {ElementKind.FUNCTION, ElementKind.MOVEMENT}
FLOW_SOURCES = {ElementKind.ENTITY, ElementKind.CONNECTOR} | PROCESS_KINDS | RULE_KINDS
FLOW_TARGETS = {ElementKind.ENTITY, ElementKind.EXIT, ElementKind.CONNECTOR} | PROCESS_KINDS | RULE_KINDS

DEFAULT_PARAMS: dict[ElementKind, dict] = {
    ElementKind.ENTITY: {"interarrival": "EXPO(10)", "first_arrival": "0",
                         "max_arrivals": 0, "batch_size": 1},
    ElementKind.FUNCTION: {"duration": "TRIA(4, 5, 6)"},
    ElementKind.MOVEMENT: {"duration": "CONST(2)"},
    ElementKind.RESOURCE: {"capacity": 1},
}

DEFAULT_NAMES: dict[ElementKind, str] = {
    ElementKind.ENTITY: "Entidade",
    ElementKind.FUNCTION: "Função",
    ElementKind.RESOURCE: "Recurso",
    ElementKind.CONTROL: "Controle",
    ElementKind.MOVEMENT: "Movimentação",
    ElementKind.RULE_AND: "&",
    ElementKind.RULE_OR: "X",
    ElementKind.RULE_ANDOR: "O",
    ElementKind.EXIT: "Fim",
    ElementKind.CONNECTOR: "A",
    ElementKind.NOTE: "Nota explicativa",
}


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class Element:
    id: str
    kind: ElementKind
    name: str
    x: float = 0.0
    y: float = 0.0
    description: str = ""
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind.value, "name": self.name,
                "x": self.x, "y": self.y, "description": self.description,
                "params": copy.deepcopy(self.params)}

    @classmethod
    def from_dict(cls, d: dict) -> "Element":
        kind = ElementKind(d["kind"])
        params = copy.deepcopy(DEFAULT_PARAMS.get(kind, {}))
        params.update(d.get("params", {}))
        return cls(id=d["id"], kind=kind, name=d.get("name", ""),
                   x=float(d.get("x", 0)), y=float(d.get("y", 0)),
                   description=d.get("description", ""), params=params)


@dataclass
class Connection:
    id: str
    kind: ConnectionKind
    source: str
    target: str
    label: str = ""
    probability: float = 1.0  # usado em regras OU / E-OU e em ramificações

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind.value, "source": self.source,
                "target": self.target, "label": self.label,
                "probability": self.probability}

    @classmethod
    def from_dict(cls, d: dict) -> "Connection":
        return cls(id=d["id"], kind=ConnectionKind(d["kind"]), source=d["source"],
                   target=d["target"], label=d.get("label", ""),
                   probability=float(d.get("probability", 1.0)))


@dataclass
class SimulationSettings:
    time_unit: str = "min"
    duration: float = 480.0
    warmup: float = 0.0
    replications: int = 5
    seed: int = 12345

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "SimulationSettings":
        s = cls()
        for k in ("time_unit", "duration", "warmup", "replications", "seed"):
            if k in d:
                setattr(s, k, type(getattr(s, k))(d[k]))
        return s


class ConnectionError_(ValueError):
    """Ligação inválida entre dois elementos."""


@dataclass
class Model:
    name: str = "Novo modelo"
    author: str = ""
    version: str = "1.0"
    description: str = ""
    elements: dict[str, Element] = field(default_factory=dict)
    connections: dict[str, Connection] = field(default_factory=dict)
    settings: SimulationSettings = field(default_factory=SimulationSettings)

    # ------------------------------------------------------------ elementos
    def _unique_name(self, kind: ElementKind) -> str:
        base = DEFAULT_NAMES[kind]
        if kind in RULE_KINDS:
            return base
        if kind == ElementKind.CONNECTOR:
            used = {e.name for e in self.elements.values() if e.kind == kind}
            for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if ch not in used:
                    return ch
            return "Z"
        n = sum(1 for e in self.elements.values() if e.kind == kind) + 1
        names = {e.name for e in self.elements.values()}
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def add_element(self, kind: ElementKind, x: float = 0, y: float = 0,
                    name: str | None = None, **params) -> Element:
        p = copy.deepcopy(DEFAULT_PARAMS.get(kind, {}))
        p.update(params)
        el = Element(new_id(), kind, name or self._unique_name(kind), x, y, params=p)
        self.elements[el.id] = el
        return el

    def remove_element(self, element_id: str) -> None:
        self.elements.pop(element_id, None)
        for cid in [c.id for c in self.connections.values()
                    if element_id in (c.source, c.target)]:
            del self.connections[cid]

    # ------------------------------------------------------------- ligações
    def check_connection(self, kind: ConnectionKind, source: str, target: str) -> tuple[str, str]:
        """Valida e normaliza (source, target). Levanta ConnectionError_."""
        if source == target:
            raise ConnectionError_("Não é possível ligar um elemento a ele próprio.")
        s, t = self.elements[source], self.elements[target]
        if kind == ConnectionKind.FLOW:
            if s.kind not in FLOW_SOURCES:
                raise ConnectionError_(f"Um fluxo não pode partir de '{KIND_LABELS[s.kind]}'.")
            if t.kind not in FLOW_TARGETS:
                raise ConnectionError_(f"Um fluxo não pode chegar a '{KIND_LABELS[t.kind]}'.")
        elif kind == ConnectionKind.RESOURCE:
            if t.kind == ElementKind.RESOURCE:
                s, t = t, s
            if s.kind != ElementKind.RESOURCE or t.kind not in PROCESS_KINDS:
                raise ConnectionError_("Recursos ligam-se apenas a Funções ou Movimentações.")
        elif kind == ConnectionKind.CONTROL:
            if t.kind == ElementKind.CONTROL:
                s, t = t, s
            if s.kind != ElementKind.CONTROL or t.kind not in PROCESS_KINDS:
                raise ConnectionError_("Controles ligam-se apenas a Funções ou Movimentações.")
        elif kind == ConnectionKind.NOTE:
            if t.kind == ElementKind.NOTE:
                s, t = t, s
            if s.kind != ElementKind.NOTE:
                raise ConnectionError_("A ligação de nota deve partir de uma Informação explicativa.")
        for c in self.connections.values():
            if c.kind == kind and c.source == s.id and c.target == t.id:
                raise ConnectionError_("Esta ligação já existe.")
        return s.id, t.id

    def add_connection(self, kind: ConnectionKind, source: str, target: str,
                       probability: float = 1.0, label: str = "") -> Connection:
        source, target = self.check_connection(kind, source, target)
        c = Connection(new_id(), kind, source, target, label, probability)
        self.connections[c.id] = c
        return c

    def outgoing(self, element_id: str, kind: ConnectionKind = ConnectionKind.FLOW) -> list[Connection]:
        return [c for c in self.connections.values() if c.source == element_id and c.kind == kind]

    def incoming(self, element_id: str, kind: ConnectionKind = ConnectionKind.FLOW) -> list[Connection]:
        return [c for c in self.connections.values() if c.target == element_id and c.kind == kind]

    def resources_of(self, element_id: str) -> list[Element]:
        return [self.elements[c.source] for c in self.incoming(element_id, ConnectionKind.RESOURCE)]

    def by_kind(self, kind: ElementKind) -> list[Element]:
        return [e for e in self.elements.values() if e.kind == kind]

    # ------------------------------------------------------- serialização
    def to_dict(self) -> dict:
        return {"format": "idefsim-studio", "format_version": 1,
                "name": self.name, "author": self.author, "version": self.version,
                "description": self.description,
                "settings": self.settings.to_dict(),
                "elements": [e.to_dict() for e in self.elements.values()],
                "connections": [c.to_dict() for c in self.connections.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> "Model":
        if d.get("format") not in (None, "idefsim-studio"):
            raise ValueError("Ficheiro não é um modelo IDEF-SIM Studio.")
        m = cls(name=d.get("name", "Modelo"), author=d.get("author", ""),
                version=str(d.get("version", "1.0")), description=d.get("description", ""),
                settings=SimulationSettings.from_dict(d.get("settings", {})))
        for ed in d.get("elements", []):
            e = Element.from_dict(ed)
            m.elements[e.id] = e
        for cd in d.get("connections", []):
            c = Connection.from_dict(cd)
            if c.source in m.elements and c.target in m.elements:
                m.connections[c.id] = c
        return m

    def clone(self) -> "Model":
        return Model.from_dict(self.to_dict())
