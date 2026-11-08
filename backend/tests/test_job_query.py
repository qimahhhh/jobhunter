from __future__ import annotations

import unittest
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.job_hunter import JobHunterAgent
from backend.app.job_query import expand_query
from backend.app.llm import LLMError
from backend.app.models import Base
from backend.app.schemas_resources import JobCreate
from backend.app.schemas_search import JobQuery, JobSearchRequest
from backend.app.services import create_job, list_jobs, search_jobs


class _FakeClient:
    def __init__(self, reply: dict[str, Any] | None = None) -> None:
        self.reply = reply if reply is not None else {"keywords": []}
        self.calls = 0
        self.last_user = ""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        self.last_user = user
        return self.reply


class _RaisingClient:
    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        raise LLMError("boom")


def _job(
    title: str,
    *,
    requirements: str = "熟悉 Python",
    company: str = "Example",
) -> JobCreate:
    return JobCreate(
        title=title,
        company=company,
        description="负责相关业务开发",
        requirements=requirements,
        employment_type="internship",
        source_name="offerxiansheng.com",
        location="北京",
    )


class ExpansionRulesTest(unittest.TestCase):
    def test_only_short_standalone_new_terms_survive(self) -> None:
        client = _FakeClient(
            {
                "keywords": [
                    "机器学习",
                    "机器学习",
                    "Python",
                    "这是一个非常长的关键词句子用来测试长度过滤",
                    "深度学习；自然语言处理",
                    "NLP",
                ]
            }
        )

        aliases, note = expand_query(JobQuery(keywords=["Python"]), client)

        # Duplicates of the user's words, sentences and over-long phrases are
        # not search terms and never reach the query.
        self.assertEqual(aliases, ["机器学习", "NLP"])
        self.assertIn("同义词", note)

    def test_expansion_is_capped(self) -> None:
        client = _FakeClient({"keywords": [f"术语{index}" for index in range(12)]})

        aliases, _ = expand_query(JobQuery(role="算法实习生"), client)

        self.assertEqual(len(aliases), 8)

    def test_a_broken_model_never_breaks_the_search(self) -> None:
        aliases, note = expand_query(JobQuery(role="算法实习生"), _RaisingClient())

        self.assertEqual(aliases, [])
        self.assertIn("跳过", note)

    def test_a_query_without_direction_is_not_sent_at_all(self) -> None:
        client = _FakeClient({"keywords": ["机器学习"]})

        aliases, note = expand_query(JobQuery(), client)

        self.assertEqual(aliases, [])
        self.assertEqual(client.calls, 0)
        self.assertIn("没有方向", note)

    def test_an_empty_reply_is_reported_as_such(self) -> None:
        aliases, note = expand_query(
            JobQuery(role="算法实习生"), _FakeClient({"keywords": []})
        )

        self.assertEqual(aliases, [])
        self.assertIn("没有给出", note)


class AliasMatchingTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def test_an_alias_only_hit_is_reported_with_a_zero_score(self) -> None:
        job = create_job(
            self.session, _job("机器学习实习生", requirements="熟悉 PyTorch")
        )

        result = JobHunterAgent().run(
            [job], JobQuery(keywords=["Python"], aliases=["机器学习"])
        )

        candidate = result.candidates[0]
        self.assertEqual(candidate.score, 0.0)
        self.assertEqual(candidate.matched, [])
        self.assertTrue(candidate.aliases_matched)
        self.assertIn("同义词", candidate.reason)

    def test_alias_hits_do_not_raise_a_real_match(self) -> None:
        job = create_job(self.session, _job("Python 机器学习实习生"))

        result = JobHunterAgent().run(
            [job], JobQuery(keywords=["Python"], aliases=["机器学习"])
        )

        # The score still answers "how much of what the user asked for",
        # and the alias hit is reported separately.
        self.assertEqual(result.candidates[0].score, 1.0)
        self.assertTrue(result.candidates[0].aliases_matched)
        self.assertIn("同义词", result.candidates[0].reason)

    def test_a_job_matching_neither_is_still_excluded(self) -> None:
        create_job(self.session, _job("市场专员", requirements="线下活动执行"))

        result = JobHunterAgent().run(
            list_jobs(self.session),
            JobQuery(keywords=["Python"], aliases=["机器学习"]),
        )

        self.assertEqual(result.candidates, [])
        self.assertEqual(len(result.excluded), 1)


class SearchWithExpansionTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def test_expansion_widens_the_shortlist_and_says_so(self) -> None:
        create_job(self.session, _job("机器学习实习生", requirements="熟悉 PyTorch"))
        client = _FakeClient({"keywords": ["机器学习"]})

        result = search_jobs(
            self.session,
            JobSearchRequest(query=JobQuery(keywords=["Python"], expand=True)),
            client=client,
        )

        self.assertEqual(result.query.aliases, ["机器学习"])
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(any("同义词" in note for note in result.notes))
        self.assertEqual(client.calls, 1)

    def test_expansion_is_not_called_unless_asked(self) -> None:
        create_job(self.session, _job("机器学习实习生"))
        client = _FakeClient({"keywords": ["机器学习"]})

        search_jobs(
            self.session,
            JobSearchRequest(query=JobQuery(keywords=["Python"])),
            client=client,
        )

        self.assertEqual(client.calls, 0)

    def test_missing_model_skips_expansion_instead_of_failing(self) -> None:
        create_job(self.session, _job("机器学习实习生"))

        result = search_jobs(
            self.session,
            JobSearchRequest(query=JobQuery(keywords=["Python"], expand=True)),
            client=None,
        )

        self.assertEqual(result.query.aliases, [])
        self.assertTrue(any("跳过" in note for note in result.notes))


if __name__ == "__main__":
    unittest.main()
