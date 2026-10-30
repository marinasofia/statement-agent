"""Create an offline review example from an existing synthetic replay fixture."""

from evals.run_evals import FIXTURES, configure


def main():
    configure("replay")
    # core.config reads UPLOAD_DIR at import time, so import it after configure().
    from agents.statement_extraction.graph import compiled_graph
    from core.config import PROJECT_ROOT
    from core.review import ReviewQueue

    outputs = PROJECT_ROOT / "outputs"

    source = FIXTURES / "clean_usd" / "statement.pdf"
    state = dict(compiled_graph.invoke({"file_path": str(source)}))
    if state.get("error"):
        raise RuntimeError(state["error"])
    db = outputs / "demo-review.sqlite"
    queue = ReviewQueue(str(db))
    identity = queue.add(state, source.read_bytes())
    preview = queue.preview(identity, str(outputs / "demo-review.html"))
    print(f"Item: {identity}")
    print(f"Preview: {preview}")
    print(f"uv run python review.py --db {db} show {identity}")


if __name__ == "__main__":
    main()
