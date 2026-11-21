"""Motor de simulação a eventos discretos (SimPy) que executa um modelo IDEF-SIM.

Semântica adotada:

* **Entidade** sem fluxo de entrada → fonte de chegadas (intervalo, lote,
  primeira chegada, máximo de chegadas). Entidade *com* fluxo de entrada →
  transformação: a entidade que chega passa a ter esse tipo.
* **Função / Movimentação** → captura todos os recursos ligados (1 unidade
  de cada), espera o tempo de processamento e os libera. Sem recursos é um
  atraso puro (capacidade infinita).
* **Regra OU (X)** → escolhe uma saída pelas probabilidades dos fluxos.
* **Regra E (&)** → com várias entradas aguarda uma entidade de cada ramo
  (montagem/junção); com várias saídas duplica a entidade (divisão paralela).
* **Regra E/OU (O)** → cada saída é seguida de forma independente com sua
  probabilidade (pelo menos uma).
* **Conexão** → a entidade salta para o conector com o mesmo nome que tem
  fluxo de saída.
* **Ponto final** → a entidade deixa o sistema.
"""
from __future__ import annotations

import math
import random
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import simpy

from . import distributions as dist
from .model import ConnectionKind as CK, ElementKind as EK, Model, PROCESS_KINDS
from .validation import has_errors, validate


class SimulationError(Exception):
    pass


# ---------------------------------------------------------------- estatística
class TimeWeighted:
    """Média ponderada no tempo, considerando apenas t ≥ warmup."""

    def __init__(self, warmup: float):
        self.warmup = warmup
        self.value = 0.0
        self.last = 0.0
        self.area = 0.0
        self.max = 0.0

    def set(self, now: float, value: float) -> None:
        start = max(self.last, self.warmup)
        if now > start:
            self.area += self.value * (now - start)
        self.last = now
        self.value = value
        if now >= self.warmup:
            self.max = max(self.max, value)

    def add(self, now: float, delta: float) -> None:
        self.set(now, self.value + delta)

    def mean(self, end: float) -> float:
        self.set(end, self.value)
        span = end - self.warmup
        return self.area / span if span > 0 else 0.0


@dataclass
class Token:
    id: int
    type: str
    created: float


@dataclass
class _ProcStats:
    queue: TimeWeighted
    busy: TimeWeighted
    waits: list = field(default_factory=list)
    services: list = field(default_factory=list)
    started: int = 0


_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t_critical(df: int) -> float:
    if df < 1:
        return float("nan")
    return _T95[df - 1] if df <= len(_T95) else 1.96


# Chave de cada indicador: (categoria, objeto, indicador)
Key = tuple[str, str, str]


@dataclass
class SummaryRow:
    category: str
    obj: str
    metric: str
    values: list[float]

    @property
    def mean(self) -> float:
        return statistics.fmean(self.values) if self.values else float("nan")

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.values) if len(self.values) > 1 else 0.0

    @property
    def half_width(self) -> float:
        n = len(self.values)
        return t_critical(n - 1) * self.stdev / math.sqrt(n) if n > 1 else float("nan")


@dataclass
class SimulationResult:
    model_name: str
    time_unit: str
    duration: float
    warmup: float
    replications: list[dict[Key, float]]

    def rows(self) -> list[SummaryRow]:
        keys: list[Key] = []
        for rep in self.replications:
            for k in rep:
                if k not in keys:
                    keys.append(k)
        return [SummaryRow(*k, [r.get(k, 0.0) for r in self.replications]) for k in keys]

    def to_csv(self) -> str:
        lines = ["Categoria;Objeto;Indicador;Média;Desvio padrão;IC95% (±);"
                 + ";".join(f"Rep {i + 1}" for i in range(len(self.replications)))]
        fmt = lambda v: "" if v != v else f"{v:.4f}".replace(".", ",")  # noqa: E731
        for r in self.rows():
            lines.append(";".join([r.category, r.obj, r.metric, fmt(r.mean), fmt(r.stdev),
                                   fmt(r.half_width)] + [fmt(v) for v in r.values]))
        return "\n".join(lines)


# ---------------------------------------------------------------- replicação
class _Replication:
    def __init__(self, model: Model, seed: int):
        self.m = model
        s = model.settings
        self.duration, self.warmup = s.duration, s.warmup
        self.env = simpy.Environment()
        self.rng = random.Random(seed)
        self.next_id = 0

        self.dists: dict[str, dist.Distribution] = {}
        for e in model.elements.values():
            if e.kind in PROCESS_KINDS:
                self.dists[e.id] = dist.parse(e.params["duration"])

        self.resources: dict[str, simpy.Resource] = {}
        self.res_busy: dict[str, TimeWeighted] = {}
        for r in model.by_kind(EK.RESOURCE):
            self.resources[r.id] = simpy.Resource(self.env, capacity=int(r.params.get("capacity", 1)))
            self.res_busy[r.id] = TimeWeighted(self.warmup)

        self.out = {e.id: model.outgoing(e.id) for e in model.elements.values()}
        self.inc = {e.id: model.incoming(e.id) for e in model.elements.values()}
        self.proc_res = {e.id: sorted(r.id for r in model.resources_of(e.id))
                         for e in model.elements.values() if e.kind in PROCESS_KINDS}
        self.proc = {eid: _ProcStats(TimeWeighted(self.warmup), TimeWeighted(self.warmup))
                     for eid in self.proc_res}

        self.joins: dict[str, dict[str, deque]] = {
            e.id: {c.id: deque() for c in self.inc[e.id]}
            for e in model.by_kind(EK.RULE_AND) if len(self.inc[e.id]) > 1}

        self.connector_exit: dict[str, str] = {}
        for e in model.by_kind(EK.CONNECTOR):
            if self.out[e.id]:
                self.connector_exit.setdefault(e.name.strip().upper(), e.id)

        self.wip = TimeWeighted(self.warmup)
        self.created: dict[str, int] = {}
        self.exited: dict[str, int] = {}
        self.consumed = 0
        self.tis: dict[str, list[float]] = {}
        self.exit_counts: dict[str, int] = {}

    # ------------------------------------------------------------ chegadas
    def _source(self, ent):
        p = ent.params
        inter = dist.parse(p.get("interarrival", "EXPO(10)"))
        first = dist.parse(p.get("first_arrival", "0")).sample(self.rng)
        max_arr = int(p.get("max_arrivals", 0) or 0)
        batch = max(1, int(p.get("batch_size", 1)))
        yield self.env.timeout(first)
        n = 0
        while max_arr == 0 or n < max_arr:
            for _ in range(batch):
                if max_arr and n >= max_arr:
                    break
                n += 1
                tok = self._new_token(ent.name)
                self.env.process(self._travel(tok, ent.id, None))
            yield self.env.timeout(inter.sample(self.rng))

    def _new_token(self, typ: str) -> Token:
        self.next_id += 1
        if self.env.now >= self.warmup:
            self.created[typ] = self.created.get(typ, 0) + 1
        self.wip.add(self.env.now, 1)
        return Token(self.next_id, typ, self.env.now)

    def _leave(self, tok: Token, where: str) -> None:
        now = self.env.now
        self.wip.add(now, -1)
        if now >= self.warmup:
            self.exited[tok.type] = self.exited.get(tok.type, 0) + 1
            self.tis.setdefault(tok.type, []).append(now - tok.created)
            self.exit_counts[where] = self.exit_counts.get(where, 0) + 1

    # ------------------------------------------------------------ percurso
    def _choose(self, conns, rng):
        total = sum(max(0.0, c.probability) for c in conns)
        if total <= 0:
            return conns[0]
        u = rng.random() * total
        acc = 0.0
        for c in conns:
            acc += max(0.0, c.probability)
            if u <= acc:
                return c
        return conns[-1]

    def _travel(self, tok: Token, node: str, via):
        m = self.m
        while True:
            el = m.elements[node]
            k = el.kind
            outs = self.out[node]

            if k in PROCESS_KINDS:
                yield from self._process(tok, el)
            elif k == EK.EXIT:
                self._leave(tok, el.name)
                return
            elif k == EK.ENTITY and via is not None:
                tok.type = el.name
            elif k == EK.CONNECTOR and not outs:
                target = self.connector_exit.get(el.name.strip().upper())
                if target is None:
                    self._leave(tok, f"Conexão {el.name}")
                    return
                node, via = target, None
                continue
            elif k == EK.RULE_AND:
                if node in self.joins:
                    queues = self.joins[node]
                    queues[via.id].append(tok)
                    if not all(queues.values()):
                        return  # aguarda os outros ramos
                    parts = [q.popleft() for q in queues.values()]
                    tok = min(parts, key=lambda t: t.created)
                    for other in parts:
                        if other is not tok:
                            self.consumed += 1
                            self.wip.add(self.env.now, -1)
                if len(outs) > 1:
                    for c in outs[1:]:
                        clone = Token(self._bump(), tok.type, tok.created)
                        self.wip.add(self.env.now, 1)
                        self.env.process(self._travel(clone, c.target, c))
                    outs = outs[:1]
            elif k == EK.RULE_ANDOR and len(outs) > 1:
                chosen = [c for c in outs if self.rng.random() < c.probability]
                if not chosen:
                    chosen = [max(outs, key=lambda c: c.probability)]
                for c in chosen[1:]:
                    clone = Token(self._bump(), tok.type, tok.created)
                    self.wip.add(self.env.now, 1)
                    self.env.process(self._travel(clone, c.target, c))
                outs = chosen[:1]

            if not outs:
                self._leave(tok, el.name)
                return
            nxt = outs[0] if len(outs) == 1 else self._choose(outs, self.rng)
            node, via = nxt.target, nxt

    def _bump(self) -> int:
        self.next_id += 1
        return self.next_id

    def _process(self, tok: Token, el):
        env = self.env
        st = self.proc[el.id]
        arrive = env.now
        st.queue.add(arrive, 1)
        held = []
        for rid in self.proc_res[el.id]:
            req = self.resources[rid].request()
            yield req
            held.append((rid, req))
        st.queue.add(env.now, -1)
        st.busy.add(env.now, 1)
        start = env.now
        for rid, _ in held:
            self.res_busy[rid].add(env.now, 1)
        yield env.timeout(self.dists[el.id].sample(self.rng))
        for rid, req in held:
            self.res_busy[rid].add(env.now, -1)
            self.resources[rid].release(req)
        st.busy.add(env.now, -1)
        if env.now >= self.warmup:
            st.waits.append(start - arrive)
            st.services.append(env.now - start)

    # ------------------------------------------------------------ execução
    def run(self) -> dict[Key, float]:
        for e in self.m.by_kind(EK.ENTITY):
            if not self.inc[e.id]:
                self.env.process(self._source(e))
        self.env.run(until=self.duration)
        end = self.duration
        span = end - self.warmup
        r: dict[Key, float] = {}
        mean = lambda xs: statistics.fmean(xs) if xs else 0.0  # noqa: E731

        types = sorted(set(self.created) | set(self.exited) | set(self.tis)
                       | {e.name for e in self.m.by_kind(EK.ENTITY)})
        tot_out = sum(self.exited.values())
        r[("Sistema", "Global", "Entidades que saíram")] = tot_out
        r[("Sistema", "Global", f"Throughput (por {self.m.settings.time_unit})")] = tot_out / span
        r[("Sistema", "Global", "WIP médio")] = self.wip.mean(end)
        r[("Sistema", "Global", "WIP no final")] = self.wip.value
        all_tis = [t for v in self.tis.values() for t in v]
        r[("Sistema", "Global", "Tempo médio no sistema")] = mean(all_tis)
        if self.consumed:
            r[("Sistema", "Global", "Entidades consumidas em junções")] = self.consumed
        for t in types:
            r[("Entidade", t, "Criadas")] = self.created.get(t, 0)
            r[("Entidade", t, "Saídas")] = self.exited.get(t, 0)
            r[("Entidade", t, "Tempo médio no sistema")] = mean(self.tis.get(t, []))
            r[("Entidade", t, "Tempo máximo no sistema")] = max(self.tis.get(t, [0]))
        for eid, st in self.proc.items():
            nm = self.m.elements[eid].name
            cat = "Função" if self.m.elements[eid].kind == EK.FUNCTION else "Movimentação"
            r[(cat, nm, "Atendimentos concluídos")] = len(st.services)
            r[(cat, nm, "Tempo médio de processamento")] = mean(st.services)
            if self.proc_res[eid]:
                r[(cat, nm, "Tempo médio em fila")] = mean(st.waits)
                r[(cat, nm, "Fila média")] = st.queue.mean(end)
                r[(cat, nm, "Fila máxima")] = st.queue.max
            r[(cat, nm, "Em processamento (média)")] = st.busy.mean(end)
        for rid, tw in self.res_busy.items():
            res = self.m.elements[rid]
            cap = int(res.params.get("capacity", 1))
            r[("Recurso", res.name, "Utilização (%)")] = 100 * tw.mean(end) / cap
            r[("Recurso", res.name, "Ocupação média (unidades)")] = tw.mean(end)
        for name, n in sorted(self.exit_counts.items()):
            r[("Saída", name, "Entidades")] = n
        return r


def run_simulation(model: Model,
                   progress: Callable[[int, int], bool | None] | None = None) -> SimulationResult:
    """Executa todas as replicações. ``progress(i, n)`` pode retornar False para cancelar."""
    issues = validate(model)
    if has_errors(issues):
        raise SimulationError("O modelo tem erros:\n" + "\n".join(
            str(i) for i in issues if i.level == "Erro"))
    s = model.settings
    reps = []
    for i in range(s.replications):
        if progress and progress(i, s.replications) is False:
            break
        reps.append(_Replication(model, s.seed + i * 7919).run())
    if progress:
        progress(len(reps), s.replications)
    return SimulationResult(model.name, s.time_unit, s.duration, s.warmup, reps)
