"""Distribuições estatísticas em notação semelhante à do Arena.

Exemplos aceites::

    5            CONST(5)        EXPO(10)        NORM(5; 0,5)
    TRIA(2, 4, 7)  UNIF(1, 3)    LOGN(5, 1)      ERLA(6, 3)   WEIB(5, 2)

Os argumentos podem ser separados por vírgula (decimal com ponto) ou por
ponto-e-vírgula (permitindo vírgula decimal, ex.: ``NORM(5,5; 0,8)``).
Amostras negativas são truncadas em zero.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass


class DistributionError(ValueError):
    pass


_SPECS: dict[str, tuple[int, str]] = {
    "CONST": (1, "CONST(valor)"),
    "EXPO": (1, "EXPO(média)"),
    "NORM": (2, "NORM(média, desvio)"),
    "TRIA": (3, "TRIA(mín, moda, máx)"),
    "UNIF": (2, "UNIF(mín, máx)"),
    "LOGN": (2, "LOGN(média, desvio)"),
    "ERLA": (2, "ERLA(média, k)"),
    "WEIB": (2, "WEIB(escala, forma)"),
}

SUPPORTED = [s for _, s in _SPECS.values()]

_RE = re.compile(r"^\s*([A-Za-z]+)\s*\((.*)\)\s*$")


@dataclass(frozen=True)
class Distribution:
    name: str
    args: tuple[float, ...]

    def sample(self, rng: random.Random) -> float:
        a = self.args
        n = self.name
        if n == "CONST":
            v = a[0]
        elif n == "EXPO":
            v = rng.expovariate(1.0 / a[0]) if a[0] > 0 else 0.0
        elif n == "NORM":
            v = rng.gauss(a[0], a[1])
        elif n == "TRIA":
            v = rng.triangular(a[0], a[2], a[1])
        elif n == "UNIF":
            v = rng.uniform(a[0], a[1])
        elif n == "LOGN":
            mean, sd = a
            s2 = math.log(1 + (sd * sd) / (mean * mean))
            v = rng.lognormvariate(math.log(mean) - s2 / 2, math.sqrt(s2))
        elif n == "ERLA":
            mean, k = a[0], int(a[1])
            v = sum(rng.expovariate(k / mean) for _ in range(k))
        elif n == "WEIB":
            v = rng.weibullvariate(a[0], a[1])
        else:  # pragma: no cover
            raise DistributionError(n)
        return max(0.0, v)

    def mean(self) -> float:
        a = self.args
        return {
            "CONST": lambda: a[0], "EXPO": lambda: a[0], "NORM": lambda: a[0],
            "TRIA": lambda: sum(a) / 3, "UNIF": lambda: (a[0] + a[1]) / 2,
            "LOGN": lambda: a[0], "ERLA": lambda: a[0],
            "WEIB": lambda: a[0] * math.gamma(1 + 1 / a[1]),
        }[self.name]()

    def __str__(self) -> str:
        return f"{self.name}({', '.join(f'{x:g}' for x in self.args)})"


def _num(s: str) -> float:
    try:
        return float(s.strip())
    except ValueError:
        raise DistributionError(f"'{s.strip()}' não é um número válido.") from None


def parse(text: str) -> Distribution:
    if text is None or not str(text).strip():
        raise DistributionError("Expressão vazia.")
    text = str(text).strip()
    m = _RE.match(text)
    if not m:
        return Distribution("CONST", (_num(text.replace(",", ".")),))
    name, body = m.group(1).upper(), m.group(2)
    if name not in _SPECS:
        raise DistributionError(f"Distribuição '{name}' desconhecida. Use: {', '.join(SUPPORTED)}")
    parts = [p.replace(",", ".") for p in body.split(";")] if ";" in body else body.split(",")
    args = tuple(_num(p) for p in parts)
    n, usage = _SPECS[name]
    if len(args) != n:
        raise DistributionError(f"{name} requer {n} parâmetro(s): {usage}")
    if name in ("EXPO", "LOGN", "ERLA") and args[0] <= 0:
        raise DistributionError(f"{name}: a média deve ser positiva.")
    if name in ("NORM", "LOGN") and args[1] < 0:
        raise DistributionError(f"{name}: o desvio não pode ser negativo.")
    if name == "TRIA" and not (args[0] <= args[1] <= args[2]):
        raise DistributionError("TRIA: deve verificar mín ≤ moda ≤ máx.")
    if name == "UNIF" and args[0] > args[1]:
        raise DistributionError("UNIF: mín deve ser ≤ máx.")
    if name == "ERLA" and (args[1] < 1 or args[1] != int(args[1])):
        raise DistributionError("ERLA: k deve ser inteiro ≥ 1.")
    if name == "WEIB" and (args[0] <= 0 or args[1] <= 0):
        raise DistributionError("WEIB: escala e forma devem ser positivas.")
    if name == "CONST" and args[0] < 0:
        raise DistributionError("CONST: o valor não pode ser negativo.")
    return Distribution(name, args)


def is_valid(text: str) -> bool:
    try:
        parse(text)
        return True
    except DistributionError:
        return False
