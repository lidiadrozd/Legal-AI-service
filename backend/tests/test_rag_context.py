from app.services.rag_context import RagChunk, RagIndex, build_rag_context, serialize_chat_context


def test_vector_search_returns_top_matches():
    index = RagIndex(
        [
            RagChunk(source="labor.txt", text="Увольнение сотрудника по статье 81 ТК РФ"),
            RagChunk(source="rent.txt", text="Договор аренды жилого помещения и сроки"),
            RagChunk(source="tax.txt", text="Налоговый вычет по НДФЛ"),
        ]
    )
    results = index.vector_search("увольнение сотрудника", top_k=2)
    assert len(results) == 2
    assert results[0].source == "labor.txt"


def test_rerank_filters_by_threshold():
    chunks = [
        RagChunk(source="a.txt", text="аренда квартиры", score=0.8),
        RagChunk(source="b.txt", text="налоги", score=0.2),
    ]
    ranked = RagIndex.rerank("аренда квартиры", chunks, threshold=0.7)
    assert len(ranked) == 1
    assert ranked[0].source == "a.txt"


def test_build_rag_context_limits_selected_chunks(monkeypatch, tmp_path):
    from app.core.config import settings

    docs_dir = tmp_path / "rag_docs"
    docs_dir.mkdir()
    (docs_dir / "labor.txt").write_text(
        "Увольнение сотрудника по инициативе работодателя.\n\n"
        "Основания увольнения по ТК РФ.",
        encoding="utf-8",
    )
    (docs_dir / "rent.txt").write_text(
        "Договор аренды жилого помещения.\n\n"
        "Срок аренды и обязанности сторон.",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(docs_dir))
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_VECTOR_TOP_K", 3)
    monkeypatch.setattr(settings, "RAG_RERANK_THRESHOLD", 0.1)
    monkeypatch.setattr(settings, "RAG_MAX_CONTEXT_CHUNKS", 2)
    monkeypatch.setattr(settings, "RAG_CHUNK_MAX_CHARS", 2000)

    import app.services.rag_context as rag_context

    rag_context._INDEX = None
    rendered = build_rag_context("увольнение сотрудника")
    assert "Релевантные фрагменты" in rendered
    assert rendered.count("[1]") == 1
    assert rendered.count("[2]") <= 1


def test_serialize_chat_context_joins_rag_and_law_changes():
    rendered = serialize_chat_context(
        {
            "rag": "Релевантные фрагменты базы знаний (сжатый контекст):\n[1] labor.txt\nТекст",
            "docs": ["Изменение: ГК РФ"],
        }
    )
    assert "Релевантные фрагменты" in rendered
    assert "Изменение: ГК РФ" in rendered
