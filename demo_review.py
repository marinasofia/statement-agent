"""Create an offline review example from an existing synthetic replay fixture."""


from evals.run_evals import FIXTURES, configure


def main():
    configure("replay")
    from agents.statement_extraction.graph import compiled_graph
    from core.review import ReviewQueue

    source = FIXTURES / "clean_usd" / "statement.pdf"
    state = dict(compiled_graph.invoke({"file_path": str(source)}))
    if state.get("error"):
        raise RuntimeError(state["error"])
    queue = ReviewQueue("outputs/demo-review.sqlite")
    identity = queue.add(state, source.read_bytes())
    queue.preview(identity, "outputs/demo-review.html")
    print(f"Item: {identity}")
    print("Preview: outputs/demo-review.html")
    print(f".venv/bin/python review.py --db outputs/demo-review.sqlite show {identity}")


if __name__ == "__main__":
    main()
