"""Gera a documentação (dicionário de dados) do modelo conceitual em HTML."""
from __future__ import annotations

import datetime as _dt
from html import escape

from .model import ConnectionKind as CK, ElementKind as EK, KIND_LABELS, Model

_PARAM_LABELS = {
    "interarrival": "Intervalo entre chegadas", "first_arrival": "Primeira chegada",
    "max_arrivals": "Máx. de chegadas (0 = ilimitado)", "batch_size": "Entidades por chegada",
    "duration": "Tempo", "capacity": "Capacidade",
}

_ORDER = [EK.ENTITY, EK.FUNCTION, EK.MOVEMENT, EK.RESOURCE, EK.CONTROL,
          EK.RULE_AND, EK.RULE_OR, EK.RULE_ANDOR, EK.CONNECTOR, EK.EXIT, EK.NOTE]


def model_to_html(model: Model, diagram_svg: str | None = None) -> str:
    u = escape(model.settings.time_unit)
    h = [f"<!doctype html><html lang='pt'><meta charset='utf-8'><title>{escape(model.name)}</title>",
         "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:2em;color:#222}"
         "table{border-collapse:collapse;margin:.5em 0 1.5em;width:100%}"
         "td,th{border:1px solid #bbb;padding:4px 8px;text-align:left;vertical-align:top}"
         "th{background:#eef}h2{border-bottom:2px solid #446;padding-bottom:2px}"
         ".diagram svg{max-width:100%;height:auto;border:1px solid #ccc}</style>",
         f"<h1>{escape(model.name)}</h1>",
         f"<p><b>Autor:</b> {escape(model.author) or '—'} &nbsp; <b>Versão:</b> {escape(model.version)}"
         f" &nbsp; <b>Gerado em:</b> {_dt.date.today():%d/%m/%Y}</p>"]
    if model.description:
        h.append(f"<p>{escape(model.description)}</p>")
    if diagram_svg:
        h.append(f"<h2>Diagrama IDEF-SIM</h2><div class='diagram'>{diagram_svg}</div>")
    s = model.settings
    h.append("<h2>Parâmetros de simulação</h2><table>"
             f"<tr><th>Unidade de tempo</th><td>{u}</td></tr>"
             f"<tr><th>Duração</th><td>{s.duration:g} {u}</td></tr>"
             f"<tr><th>Aquecimento</th><td>{s.warmup:g} {u}</td></tr>"
             f"<tr><th>Replicações</th><td>{s.replications}</td></tr>"
             f"<tr><th>Semente</th><td>{s.seed}</td></tr></table>")
    for kind in _ORDER:
        els = sorted(model.by_kind(kind), key=lambda e: e.name)
        if not els:
            continue
        h.append(f"<h2>{KIND_LABELS[kind]} ({len(els)})</h2><table>"
                 "<tr><th>Nome</th><th>Parâmetros</th><th>Ligações</th><th>Descrição</th></tr>")
        for e in els:
            params = "<br>".join(f"{_PARAM_LABELS.get(k, k)}: {escape(str(v))}"
                                 for k, v in e.params.items())
            links = []
            for c in model.outgoing(e.id):
                p = f" (p={c.probability:g})" if len(model.outgoing(e.id)) > 1 else ""
                links.append(f"→ {escape(model.elements[c.target].name)}{p}")
            for c in model.incoming(e.id):
                links.append(f"← {escape(model.elements[c.source].name)}")
            for ck, txt in ((CK.RESOURCE, "Recurso"), (CK.CONTROL, "Controle")):
                for c in model.incoming(e.id, ck):
                    links.append(f"{txt}: {escape(model.elements[c.source].name)}")
                for c in model.outgoing(e.id, ck):
                    links.append(f"Usado em: {escape(model.elements[c.target].name)}")
            h.append(f"<tr><td>{escape(e.name)}</td><td>{params or '—'}</td>"
                     f"<td>{'<br>'.join(links) or '—'}</td><td>{escape(e.description) or '—'}</td></tr>")
        h.append("</table>")
    h.append("</html>")
    return "\n".join(h)
