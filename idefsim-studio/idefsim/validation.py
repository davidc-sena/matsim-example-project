"""Verificação de consistência de um modelo IDEF-SIM."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass

from . import distributions as dist
from .model import (ConnectionKind as CK, ElementKind as EK, KIND_LABELS,
                    PROCESS_KINDS, RULE_KINDS, Model)

ERROR, WARNING, INFO = "Erro", "Aviso", "Info"


@dataclass
class Issue:
    level: str
    message: str
    element_id: str | None = None

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


def _reachable(model: Model) -> set[str]:
    seen: set[str] = set()
    q = deque(e.id for e in model.by_kind(EK.ENTITY) if not model.incoming(e.id))
    connectors: dict[str, list[str]] = {}
    for e in model.by_kind(EK.CONNECTOR):
        connectors.setdefault(e.name.strip().upper(), []).append(e.id)
    while q:
        nid = q.popleft()
        if nid in seen:
            continue
        seen.add(nid)
        for c in model.outgoing(nid):
            q.append(c.target)
        el = model.elements[nid]
        if el.kind == EK.CONNECTOR:
            q.extend(connectors.get(el.name.strip().upper(), []))
    return seen


def validate(model: Model) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda lvl, msg, eid=None: issues.append(Issue(lvl, msg, eid))  # noqa: E731

    sources = [e for e in model.by_kind(EK.ENTITY) if not model.incoming(e.id)]
    if not sources:
        add(ERROR, "O modelo não tem nenhuma Entidade de entrada (sem fluxos a chegar).")
    if not model.by_kind(EK.EXIT):
        add(WARNING, "O modelo não tem Ponto final; as entidades saem onde o fluxo terminar.")

    for e in model.elements.values():
        label = f"{KIND_LABELS[e.kind]} '{e.name}'"
        outs = model.outgoing(e.id)
        ins = model.incoming(e.id)

        if e.kind == EK.ENTITY and not ins:
            if not outs:
                add(ERROR, f"{label} não tem fluxo de saída.", e.id)
            for key, nm in (("interarrival", "intervalo entre chegadas"),
                            ("first_arrival", "primeira chegada")):
                try:
                    d = dist.parse(e.params.get(key, ""))
                    if key == "interarrival" and d.mean() <= 0:
                        add(ERROR, f"{label}: o {nm} deve ter média positiva.", e.id)
                except dist.DistributionError as ex:
                    add(ERROR, f"{label}: {nm} inválido — {ex}", e.id)
            if int(e.params.get("batch_size", 1)) < 1:
                add(ERROR, f"{label}: tamanho do lote deve ser ≥ 1.", e.id)

        if e.kind in PROCESS_KINDS:
            try:
                dist.parse(e.params.get("duration", ""))
            except dist.DistributionError as ex:
                add(ERROR, f"{label}: tempo inválido — {ex}", e.id)
            if not ins:
                add(WARNING, f"{label} não recebe nenhum fluxo de entidade.", e.id)
            if not outs:
                add(WARNING, f"{label} não tem fluxo de saída; as entidades deixam o sistema aqui.", e.id)

        if e.kind == EK.RESOURCE:
            if int(e.params.get("capacity", 1)) < 1:
                add(ERROR, f"{label}: a capacidade deve ser ≥ 1.", e.id)
            if not model.outgoing(e.id, CK.RESOURCE):
                add(WARNING, f"{label} não está associado a nenhuma função.", e.id)

        if e.kind in RULE_KINDS:
            if not ins:
                add(ERROR, f"{label} não recebe nenhum fluxo.", e.id)
            if not outs:
                add(ERROR, f"{label} não tem fluxos de saída.", e.id)
            if e.kind == EK.RULE_AND and len(ins) <= 1 and len(outs) <= 1:
                add(INFO, f"{label} tem apenas uma entrada e uma saída (não divide nem junta).", e.id)
            if e.kind in (EK.RULE_OR, EK.RULE_ANDOR) and len(ins) > 1 and len(outs) <= 1:
                pass  # junção simples
            if e.kind == EK.RULE_OR and len(outs) > 1:
                total = sum(c.probability for c in outs)
                if total <= 0:
                    add(ERROR, f"{label}: as probabilidades de saída somam zero.", e.id)
                elif abs(total - 1) > 1e-6:
                    add(WARNING, f"{label}: as probabilidades somam {total:g} e serão normalizadas.", e.id)

        if e.kind in PROCESS_KINDS and len(outs) > 1:
            total = sum(c.probability for c in outs)
            if total <= 0:
                add(ERROR, f"{label}: as probabilidades de saída somam zero.", e.id)
            else:
                add(INFO, f"{label} tem {len(outs)} saídas sem regra explícita; "
                          "será tratado como OU (X) pelas probabilidades.", e.id)

        if e.kind == EK.EXIT and outs:
            add(ERROR, f"{label} não pode ter fluxos de saída.", e.id)

        if e.kind == EK.CONTROL and not model.outgoing(e.id, CK.CONTROL):
            add(INFO, f"{label} não está associado a nenhuma função.", e.id)

    # conectores: cada rótulo precisa de um par entrada/saída
    groups: dict[str, list] = {}
    for e in model.by_kind(EK.CONNECTOR):
        groups.setdefault(e.name.strip().upper(), []).append(e)
    for name, els in groups.items():
        has_in = any(model.incoming(e.id) for e in els)
        has_out = any(model.outgoing(e.id) for e in els)
        if not (has_in and has_out):
            add(ERROR, f"Conexão '{name}' precisa de um conector de chegada e outro de partida "
                       "com o mesmo nome.", els[0].id)

    names = Counter((e.kind, e.name.strip().lower()) for e in model.elements.values()
                    if e.kind in PROCESS_KINDS | {EK.RESOURCE, EK.ENTITY})
    for (kind, nm), n in names.items():
        if n > 1:
            add(WARNING, f"Existem {n} elementos '{KIND_LABELS[kind]}' com o nome '{nm}'.")

    reach = _reachable(model)
    for e in model.elements.values():
        if (e.kind in PROCESS_KINDS | RULE_KINDS | {EK.EXIT}) and e.id not in reach and sources:
            add(WARNING, f"{KIND_LABELS[e.kind]} '{e.name}' não é alcançável por nenhuma entidade.", e.id)

    s = model.settings
    if s.duration <= 0:
        add(ERROR, "A duração da simulação deve ser positiva.")
    if not (0 <= s.warmup < s.duration):
        add(ERROR, "O aquecimento deve ser ≥ 0 e menor que a duração.")
    if s.replications < 1:
        add(ERROR, "O número de replicações deve ser ≥ 1.")

    order = {ERROR: 0, WARNING: 1, INFO: 2}
    issues.sort(key=lambda i: order[i.level])
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == ERROR for i in issues)
