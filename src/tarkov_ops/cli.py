"""tarkov-ops command line."""

from __future__ import annotations

import logging
from typing import Any

import typer
from rich.console import Console
from rich.tree import Tree

from tarkov_ops import __version__
from tarkov_ops.settings import get_settings

app = typer.Typer(help="PvE Tarkov progress, needs, stash and verdicts.", no_args_is_help=True)
progress_app = typer.Typer(help="TarkovTracker progress.", no_args_is_help=True)
app.add_typer(progress_app, name="progress")
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
