"""tarkov-ops command line."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.tree import Tree

from tarkov_ops import __version__
from tarkov_ops.settings import get_settings

app = typer.Typer(help="PvE Tarkov progress, needs, stash and verdicts.", no_args_is_help=True)
progress_app = typer.Typer(help="TarkovTracker progress.", no_args_is_help=True)
app.add_typer(progress_app, name="progress")
gamedata_app = typer.Typer(help="json.tarkov.dev reference data (PvE).", no_args_is_help=True)
app.add_typer(gamedata_app, name="gamedata")
needs_app = typer.Typer(
    help="Items still needed for tasks, hideout and Kappa.", no_args_is_help=True
)
app.add_typer(needs_app, name="needs")
console = Console()


@app.callback()
def _root(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging.")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # httpx logs full request lines; never let it print headers.
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def version() -> None:
    console.print(f"tarkov-ops {__version__}")


@progress_app.command("raw")
def progress_raw(
    show: bool = typer.Option(True, help="Print a shape summary of the payload."),
) -> None:
    """GET /progress once and save the raw JSON to docs/samples/progress.json."""
    from tarkov_ops.progress.client import TrackerClient

    s = get_settings()
    dest = s.samples_dir / "progress.json"
    with TrackerClient(s) as c:
        resp = c.dump_progress(dest)
    console.print(f"[green]saved[/] {dest} ({dest.stat().st_size:,} bytes)")
    console.print(f"quota remaining: {resp.rate_remaining}/{resp.rate_limit}  etag: {resp.etag}")
    if show and resp.data is not None:
        console.print(_shape_tree(resp.data))


@progress_app.command("token")
def progress_token() -> None:
    """GET /token: verify the token, show permissions and game mode (never the token)."""
    from tarkov_ops.progress.client import TrackerClient
    from tarkov_ops.progress.models import TokenInfoResponse

    with TrackerClient(get_settings()) as c:
        resp = c.token_info()
    info = TokenInfoResponse.model_validate(resp.data)
    console.print(
        f"mode=[bold]{info.gameMode}[/] permissions={info.permissions} "
        f"note={info.note!r} calls={info.calls} quota={resp.rate_remaining}/{resp.rate_limit}"
    )


@gamedata_app.command("refresh")
def gamedata_refresh(
    force: bool = typer.Option(False, "--force", "-f", help="Refetch even if fresh (<12h)."),
) -> None:
    """Download tasks, hideout, items and traders from json.tarkov.dev into data/gamedata/."""
    from tarkov_ops.gamedata import fetch

    d = fetch.cache_dir()
    if not force and not fetch.is_stale(d):
        console.print(f"[dim]cache fresh[/] {d} (use --force to refetch)")
        return
    sizes = fetch.refresh()
    total = sum(sizes.values())
    console.print(f"[green]refreshed[/] {len(sizes)} files, {total / 1e6:.1f} MB -> {d}")


@gamedata_app.command("status")
def gamedata_status() -> None:
    """Show when each endpoint was last fetched."""
    from tarkov_ops.gamedata import fetch

    d = fetch.cache_dir()
    meta = fetch.read_meta(d)
    if not meta:
        console.print("[yellow]no cache[/] run: tarkov-ops gamedata refresh")
        return
    for name, ts in meta.items():
        console.print(f"{name:10} {ts}")
    console.print("stale" if fetch.is_stale(d) else "[green]fresh[/]")


def _load_progress(source: str):
    """source: 'file' (docs/samples/progress.json), 'live' (GET /progress), or 'none'."""
    from tarkov_ops.progress.models import ProgressResponse

    if source == "none":
        return None
    s = get_settings()
    if source == "live":
        from tarkov_ops.progress.client import TrackerClient

        dest = s.samples_dir / "progress.json"
        with TrackerClient(s) as c:
            c.dump_progress(dest)
    p = s.samples_dir / "progress.json"
    if not p.exists():
        raise typer.BadParameter(f"{p} missing; run `tarkov-ops progress raw` or use --source live")
    raw = json.loads(p.read_text(encoding="utf-8"))
    # dump_progress saves the whole response body; accept either shape
    return ProgressResponse.model_validate(raw).data if "data" in raw else None


@needs_app.command("show")
def needs_show(
    source: str = typer.Option("file", help="Progress source: file | live | none."),
    limit: int = typer.Option(60, help="Max item rows."),
    kappa: bool = typer.Option(False, help="Include Collector (Kappa) items."),
    window: int = typer.Option(5, help="Levels ahead to count upcoming tasks."),
) -> None:
    """Table of items still needed, most urgent first."""
    from rich.table import Table

    from tarkov_ops.gamedata import load_gamedata
    from tarkov_ops.needs import compute_needs

    gd = load_gamedata()
    prog = _load_progress(source)
    res = compute_needs(gd, prog, level_window=window, include_kappa=kappa)
    if res.task_state:
        st = res.task_state
        console.print(
            f"level {res.player_level} · tasks done {len(st.done)} · "
            f"available {len(st.available)} · upcoming {len(st.upcoming)}"
        )
    else:
        console.print("[yellow]no progress loaded[/]: showing every task and hideout level")
    t = Table("Item", "Need", "FIR", "Most urgent", "Reasons")
    for n in res.items[:limit]:
        reasons = "; ".join(f"{s.label} x{s.count}" for s in n.sources[:3])
        if len(n.sources) > 3:
            reasons += f"; +{len(n.sources) - 3} more"
        t.add_row(n.name, str(n.total), str(n.fir_total or ""), n.urgency.label, reasons)
    console.print(t)
    if len(res.items) > limit:
        console.print(f"[dim]… {len(res.items) - limit} more items[/]")
    if res.any_of:
        console.print(f"[bold]{len(res.any_of)} 'any of' objectives[/] (e.g. any 3 meds):")
        for a in res.any_of[:10]:
            console.print(f"  {a.task}: {a.label} x{a.count}{' FIR' if a.fir else ''}")


@needs_app.command("export")
def needs_export(
    source: str = typer.Option("file", help="Progress source: file | live | none."),
    dest: str = typer.Option("", help="Output path (default out/needs.json)."),
    window: int = typer.Option(5),
) -> None:
    """Write needs as JSON for the dashboard / Field Card pages."""
    from tarkov_ops.gamedata import load_gamedata
    from tarkov_ops.needs import compute_needs
    from tarkov_ops.needs.export import needs_to_json

    gd = load_gamedata()
    res = compute_needs(gd, _load_progress(source), level_window=window, include_kappa=True)
    out = get_settings().out_dir / "needs.json" if not dest else Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(needs_to_json(gd, res), indent=1), encoding="utf-8")
    console.print(f"[green]wrote[/] {out} ({len(res.items)} items, {len(res.any_of)} any-of)")


fieldcard_app = typer.Typer(
    help="Field Card page (Ammo...Loot, Needs, Routes).", no_args_is_help=True
)
app.add_typer(fieldcard_app, name="fieldcard")


@fieldcard_app.command("build")
def fieldcard_build(
    source: str = typer.Option("file", help="Progress source: file | live | none."),
    level: int = typer.Option(0, help="Player level if the tracker's is stale (0 = tracker)."),
    dest: str = typer.Option("", help="Output folder (default out/fieldcard)."),
    icons: bool = typer.Option(True, help="Embed item icons in loot.json."),
) -> None:
    """Write index.html + data/{gear,loot,needs,routes}.json for publishing."""
    import shutil

    from tarkov_ops.gamedata import load_gamedata
    from tarkov_ops.publish import loot as loot_mod
    from tarkov_ops.publish.fieldcard import build_needs_and_routes

    s = get_settings()
    out = Path(dest) if dest else s.out_dir / "fieldcard"
    (out / "data").mkdir(parents=True, exist_ok=True)
    assets = Path(__file__).parent / "publish" / "fieldcard_assets"
    shutil.copyfile(assets / "template.html", out / "index.html")
    shutil.copyfile(assets / "gear.json", out / "data" / "gear.json")
    gd = load_gamedata()
    n = loot_mod.export(gd, s.data_dir, out / "data" / "loot.json", icons=icons)
    console.print(f"loot: {n} items")
    prog = _load_progress(source)
    if prog is None:
        console.print("[yellow]no progress[/]: needs.json / routes.json not written")
        return
    needs, routes = build_needs_and_routes(gd, prog, s.data_dir, level=level or None)
    (out / "data" / "needs.json").write_text(json.dumps(needs, separators=(",", ":")), "utf-8")
    (out / "data" / "routes.json").write_text(json.dumps(routes, separators=(",", ":")), "utf-8")
    console.print(
        f"[green]built[/] {out}: {len(needs['started'])} started tasks, "
        f"{len(needs['taskItems'])} task items, {len(routes)} route groups"
    )


def _shape_tree(data: Any, label: str = "root", max_keys: int = 40) -> Tree:
    """Render the shape (keys + types + sizes) of a JSON payload, not its values."""
    tree = Tree(f"[bold]{label}[/] {_describe(data)}")
    _walk(data, tree, max_keys)
    return tree


def _describe(v: Any) -> str:
    if isinstance(v, dict):
        return f"[dim]object[{len(v)} keys][/]"
    if isinstance(v, list):
        return f"[dim]array[{len(v)}][/]"
    return f"[dim]{type(v).__name__}[/]"


def _walk(v: Any, node: Tree, max_keys: int) -> None:
    if isinstance(v, dict):
        for i, (k, child) in enumerate(v.items()):
            if i >= max_keys:
                node.add(f"[dim]… {len(v) - max_keys} more keys[/]")
                break
            sub = node.add(f"{k} {_describe(child)}")
            _walk(child, sub, max_keys)
    elif isinstance(v, list) and v:
        sub = node.add(f"[0] {_describe(v[0])}")
        _walk(v[0], sub, max_keys)


if __name__ == "__main__":
    app()
