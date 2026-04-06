from docubot import DocuBot


def test_retrieve_returns_results_for_known_query():
    bot = DocuBot()
    results = bot.retrieve("auth token")
    assert len(results) > 0


def test_retrieve_returns_correct_file_for_auth_query():
    bot = DocuBot()
    results = bot.retrieve("auth token")
    filenames = [fname for fname, _ in results]
    assert "AUTH.md" in filenames


def test_retrieve_returns_empty_for_unknown_topic():
    bot = DocuBot()
    results = bot.retrieve("xyzpaymentprocessingxyz")
    assert results == []


def test_retrieval_only_answer_contains_snippet():
    bot = DocuBot()
    answer = bot.answer_retrieval_only("database connection")
    assert "DATABASE.md" in answer


def test_retrieval_only_returns_refusal_for_unknown_topic():
    bot = DocuBot()
    answer = bot.answer_retrieval_only("xyzpaymentprocessingxyz")
    assert "do not know" in answer.lower()


def test_rag_raises_without_llm_client():
    bot = DocuBot(llm_client=None)
    try:
        bot.answer_rag("auth token")
        assert False, "Should have raised RuntimeError"
    except RuntimeError:
        pass
