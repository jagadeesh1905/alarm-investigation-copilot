
from rag_pipeline import search_procedures

queries = [
    "What should be investigated for a motor trip?",
    "What is the company's employee leave policy?",
    "How do I configure a Kubernetes cluster?",
]

for query in queries:
    print("\n" + "=" * 70)
    print(f"QUERY: {query}")

    try:
        results = search_procedures(query, top_k=3)

        if not results:
            print("PASS: No relevant procedure evidence returned.")
            continue

        print(f"Returned {len(results)} result(s):")

        for result in results:
            print(
                f"- {result.get('title', 'Untitled')} | "
                f"distance={result.get('distance')} | "
                f"status={result.get('approval_status')}"
            )

        if "motor trip" in query.lower():
            print("REVIEW: Check that the returned evidence is relevant.")
        else:
            print(
                "REVIEW: Check whether these results are genuinely "
                "relevant to the query."
            )

    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
