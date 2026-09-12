# -*- coding: utf-8 -*-
"""Tunable strategy parameter space definitions."""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator


class ParameterType(str, Enum):
    NUMERIC = "numeric"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"


@dataclass(frozen=True)
class Parameter:
    """Single tunable parameter."""

    name: str
    param_type: str
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple[Any, ...] = ()
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "param_type": self.param_type,
            "low": self.low,
            "high": self.high,
            "step": self.step,
            "choices": list(self.choices),
            "default": self.default,
        }


@dataclass
class ParameterConstraint:
    """Cross-parameter constraint."""

    description: str
    check: Any  # callable(params: dict) -> bool

    def satisfied(self, params: dict[str, Any]) -> bool:
        return bool(self.check(params))


@dataclass
class ParameterSpace:
    """Collection of tunable parameters with constraints and fixed values."""

    parameters: list[Parameter] = field(default_factory=list)
    constraints: list[ParameterConstraint] = field(default_factory=list)
    fixed: dict[str, Any] = field(default_factory=dict)

    def add(self, param: Parameter) -> ParameterSpace:
        self.parameters.append(param)
        return self

    def add_constraint(self, description: str, check: Any) -> ParameterSpace:
        self.constraints.append(ParameterConstraint(description, check))
        return self

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for p in self.parameters:
            if p.name not in params:
                errors.append(f"Missing parameter: {p.name}")
                continue
            val = params[p.name]
            if p.param_type == ParameterType.NUMERIC.value:
                if not isinstance(val, (int, float)):
                    errors.append(f"{p.name} must be numeric")
                elif p.low is not None and val < p.low:
                    errors.append(f"{p.name} below minimum {p.low}")
                elif p.high is not None and val > p.high:
                    errors.append(f"{p.name} above maximum {p.high}")
            elif p.param_type == ParameterType.INTEGER.value:
                if not isinstance(val, int) or isinstance(val, bool):
                    errors.append(f"{p.name} must be integer")
                elif p.low is not None and val < p.low:
                    errors.append(f"{p.name} below minimum {p.low}")
                elif p.high is not None and val > p.high:
                    errors.append(f"{p.name} above maximum {p.high}")
            elif p.param_type == ParameterType.BOOLEAN.value:
                if not isinstance(val, bool):
                    errors.append(f"{p.name} must be boolean")
            elif p.param_type == ParameterType.CATEGORICAL.value:
                if val not in p.choices:
                    errors.append(f"{p.name} not in choices {p.choices}")
        for c in self.constraints:
            if not c.satisfied(params):
                errors.append(f"Constraint violated: {c.description}")
        return errors

    def _values_for(self, param: Parameter) -> list[Any]:
        if param.name in self.fixed:
            return [self.fixed[param.name]]
        if param.param_type == ParameterType.BOOLEAN.value:
            return [True, False]
        if param.param_type == ParameterType.CATEGORICAL.value:
            return list(param.choices)
        if param.param_type == ParameterType.INTEGER.value:
            low = int(param.low or 0)
            high = int(param.high or low)
            step = int(param.step or 1)
            return list(range(low, high + 1, step))
        if param.param_type == ParameterType.NUMERIC.value:
            low = float(param.low or 0.0)
            high = float(param.high or low)
            step = float(param.step or 1.0)
            vals: list[float] = []
            cur = low
            while cur <= high + 1e-9:
                vals.append(round(cur, 6))
                cur += step
            return vals
        return []

    def grid_combinations(self) -> Iterator[dict[str, Any]]:
        """Exhaustive deterministic grid over all parameter values."""
        names = [p.name for p in self.parameters if p.name not in self.fixed]
        value_lists = [self._values_for(p) for p in self.parameters if p.name not in self.fixed]
        for combo in itertools.product(*value_lists):
            params = dict(self.fixed)
            params.update(dict(zip(names, combo)))
            if self.validate_params(params):
                continue
            yield params

    def random_sample(self, n: int, *, seed: int = 42) -> list[dict[str, Any]]:
        """Deterministic seeded random search samples."""
        rng = random.Random(seed)
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        attempts = 0
        max_attempts = n * 50
        while len(out) < n and attempts < max_attempts:
            attempts += 1
            params = dict(self.fixed)
            for p in self.parameters:
                if p.name in self.fixed:
                    continue
                vals = self._values_for(p)
                if vals:
                    params[p.name] = rng.choice(vals)
            key = str(sorted(params.items()))
            if key in seen:
                continue
            if self.validate_params(params):
                continue
            seen.add(key)
            out.append(params)
        if len(out) < n:
            for params in self.grid_combinations():
                key = str(sorted(params.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(params)
                if len(out) >= n:
                    break
        return out

    def defaults(self) -> dict[str, Any]:
        params = dict(self.fixed)
        for p in self.parameters:
            if p.name not in params:
                params[p.name] = p.default
        return params

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": [p.to_dict() for p in self.parameters],
            "fixed": dict(self.fixed),
            "constraint_count": len(self.constraints),
        }
