import pytest

from idefsim import distributions as dist
from idefsim.examples import montagem, usinagem_inspecao
from idefsim.model import ConnectionError_, ConnectionKind as CK, ElementKind as EK, Model
from idefsim.simulation import run_simulation
from idefsim.storage import load_model, save_model
from idefsim.validation import has_errors, validate


def test_parse_distributions():
    assert dist.parse("5").mean() == 5
    assert dist.parse("2,5").mean() == 2.5
    assert dist.parse("tria(1,2,3)").mean() == 2
    assert dist.parse("NORM(5; 0,5)").args == (5.0, 0.5)
    for bad in ("", "TRIA(3,2,1)", "FOO(1)", "EXPO(0)", "NORM(1)"):
        with pytest.raises(dist.DistributionError):
            dist.parse(bad)


def test_connection_rules():
    m = Model()
    e = m.add_element(EK.ENTITY)
    f = m.add_element(EK.FUNCTION)
    r = m.add_element(EK.RESOURCE)
    m.add_connection(CK.FLOW, e.id, f.id)
    c = m.add_connection(CK.RESOURCE, f.id, r.id)  # normalizado
    assert (c.source, c.target) == (r.id, f.id)
    with pytest.raises(ConnectionError_):
        m.add_connection(CK.FLOW, e.id, f.id)
    with pytest.raises(ConnectionError_):
        m.add_connection(CK.FLOW, r.id, f.id)
    m.remove_element(f.id)
    assert not m.connections


def test_roundtrip(tmp_path):
    m = usinagem_inspecao()
    p = tmp_path / "m.idefsim"
    save_model(m, p)
    m2 = load_model(p)
    assert m2.to_dict() == m.to_dict()


def test_validation_examples_ok():
    assert not has_errors(validate(usinagem_inspecao()))
    assert not has_errors(validate(montagem()))
    assert has_errors(validate(Model()))


def test_simulation_mm1_utilization():
    m = Model()
    m.settings.duration, m.settings.warmup, m.settings.replications = 20000, 1000, 3
    e = m.add_element(EK.ENTITY, interarrival="EXPO(10)")
    f = m.add_element(EK.FUNCTION, duration="EXPO(8)")
    r = m.add_element(EK.RESOURCE)
    x = m.add_element(EK.EXIT)
    m.add_connection(CK.FLOW, e.id, f.id)
    m.add_connection(CK.FLOW, f.id, x.id)
    m.add_connection(CK.RESOURCE, r.id, f.id)
    res = {(row.category, row.metric): row.mean for row in run_simulation(m).rows()}
    assert 75 < res[("Recurso", "Utilização (%)")] < 85        # ρ = 0.8
    assert 25 < res[("Sistema", "Tempo médio no sistema")] < 55  # W = 40


def test_simulation_examples_run():
    r = run_simulation(usinagem_inspecao())
    rows = {(x.obj, x.metric): x for x in r.rows()}
    assert rows[("Expedição", "Entidades")].mean > 0
    assert rows[("Retrabalhar", "Atendimentos concluídos")].mean > 0
    r2 = run_simulation(montagem())
    rows2 = {(x.obj, x.metric): x.mean for x in r2.rows()}
    assert rows2[("Produto", "Saídas")] > 0
    assert rows2[("Global", "Entidades consumidas em junções")] > 0
    assert "Categoria;Objeto" in r2.to_csv()
