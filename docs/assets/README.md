# docs/assets

Drop image and GIF assets referenced by the top-level `README.md` here.

## Recommended assets

| File | What it shows | How to make it |
|---|---|---|
| `hero.png` | Wide banner showing the architecture / catalogue count | Use excalidraw.com or export the mermaid diagram from README as PNG (mermaid live editor → export). 1600×640 recommended. |
| `tests.png` | Screenshot of `pytest: 200 passed` | Run `uv run python -m pytest tests/ -q` in a nice terminal (iTerm2, Warp) and screenshot. |
| `demo.gif` | 15-30s recording of scaffolding a new server + running tests | See "Recording a demo GIF" below. |
| `architecture.png` | Larger rendered architecture diagram | Export the top-of-README mermaid graph via [mermaid.live](https://mermaid.live/). |
| `gateway.png` | Screenshot of the gateway responding on port 8000 | `curl http://localhost:8000/health | jq` in a terminal, screenshot. |

## Recording a demo GIF

```bash
# Option A — asciinema + agg (cleanest terminal GIFs)
brew install asciinema
cargo install --git https://github.com/asciinema/agg
asciinema rec demo.cast -c "make demo"
agg demo.cast demo.gif --font-size 16 --theme monokai

# Option B — termtosvg (SVG animation, GitHub-embeddable via <img>)
pipx install termtosvg
termtosvg demo.svg -c "make demo"
```

`make demo` runs a scripted walkthrough (add one to the top-level `Makefile` — e.g. show `mcp-create`, then `pytest`).

## Social preview

Upload a 1280×640 PNG to **Settings → Social preview** on the repo page. That is the image that appears when the repo link is shared on Twitter, Slack, etc.
