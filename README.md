# Trader-IA

Autonomous quantitative research, backtesting and paper-trading platform.

> **Simulation only.** This system runs exclusively in backtesting, simulation, paper
> trading, shadow trading and research. It contains no adapter to any real trading venue,
> requires no financial credentials, and cannot transfer, custody or risk real money.
>
> **No performance claim is made.** Results describe what an experiment produced under
> stated conditions. They are not evidence about future returns.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Quick start

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

Full instructions: [docs/QUICKSTART.md](docs/QUICKSTART.md).
