"""Vuelca las firmas públicas de los módulos tocados (y los campos de los modelos) para compararlas entre árboles."""
import dataclasses
import inspect

import tia.backtest as B
import tia.backtest.engine as E
import tia.backtest.result as R
import tia.execution.paper as P

out = []
for mod in (E, R, P):
    for name, obj in sorted(vars(mod).items()):
        if name.startswith("_") or getattr(obj, "__module__", None) != mod.__name__:
            continue
        if inspect.isclass(obj):
            out.append(f"class {mod.__name__}.{name}")
            if dataclasses.is_dataclass(obj):
                out.append(f"  dataclass fields: {[f.name for f in dataclasses.fields(obj)]}")
            if hasattr(obj, "model_fields"):
                out.append(f"  model fields: {list(obj.model_fields)}")
            for m, f in sorted(vars(obj).items()):
                if m.startswith("_") and m != "__init__":
                    continue
                if callable(f) or isinstance(f, (property, staticmethod, classmethod)):
                    try:
                        sig = str(inspect.signature(f if not isinstance(f, (staticmethod, classmethod)) else f.__func__))
                    except (TypeError, ValueError):
                        sig = "(property)" if isinstance(f, property) else "(?)"
                    out.append(f"  {m}{sig}")
        elif callable(obj):
            out.append(f"def {mod.__name__}.{name}{inspect.signature(obj)}")
out.append(f"tia.backtest.__all__ = {sorted(getattr(B, '__all__', []))}")
print("\n".join(out))
