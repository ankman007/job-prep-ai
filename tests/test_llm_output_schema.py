"""Validation of LLM output against the JSON schemas in app/schemas/response.py,
plus the JSON-parsing path (GeminiLLM.generate) and the orchestration in
get_interview_cheatsheet. The LLM client is always mocked.

Note: the schemas are plain JSON-Schema dicts (sent to Gemini as
``response_json_schema``), not Pydantic models, so we validate with jsonschema.
"""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

jsonschema = pytest.importorskip("jsonschema")

from app.schemas.response import candidate_schema, interviewer_schema  # noqa: E402

RESPONSE_PY = Path(__file__).resolve().parent.parent / "backend" / "app" / "schemas" / "response.py"


def _te(title="t", description="d", **extra):
    return {"title": title, "description": description, **extra}


VALID_CANDIDATE = {
    "company": "Acme",
    "role": "Backend Engineer",
    "swot_analysis": {
        "strengths": [_te()], "weaknesses": [_te()],
        "opportunities": [_te()], "threats": [],
    },
    "skill_assessment": {
        "match_percentage": 72,
        "matched_skills": [_te(rating="5/5")],
        "partial_matches": [_te(rating="3/5")],
        "missing_skills": [_te()],
    },
    "concept_refresh": [{
        "topic": "Async IO", "context": "JD", "review_notes": "event loop",
        "video_resource": "https://example.com/v",
    }],
    "interview_questions": [{
        "category": "Technical", "difficulty": "Medium",
        "question": "What is GIL?", "answer": "...",
    }],
    "company_insights": {
        "company_overview": "o", "culture_points": ["c"], "company_values": ["v"],
        "interview_style": "s", "expectations": "e", "additional_info": "a",
    },
}

VALID_INTERVIEWER = {
    "candidate_overview": {
        "full_name": "Jane Doe", "current_job_title": "SWE", "email": "j@x.io",
        "location": "KTM", "candidate_summary": "s", "top_skills": ["Python"],
    },
    "compatibility_score": {
        "overall_score": 80, "match": "good", "technical_skills_score": 85,
        "education_score": 70, "experience_score": 75, "cultural_fit_score": 90,
    },
    "skills_assessment": {"data": {
        "skillsByCategory": [{"category": "Backend", "skills": [
            {"name": "Python", "level": 4, "required": 3, "status": "exceeds"},
        ]}],
        "skillsDistribution": {"exceeds": 1, "meets": 0, "below": 0, "missing": 0},
    }},
    "education": [{"degree_name": "BSc", "institution": "TU", "notable_points": []}],
    "experience": [{"title": "SWE", "company": "X", "responsibilities": ["r"],
                    "relevance_to_job": "High"}],
    "skill_gaps_and_concerns": [{"skill_name": "K8s", "recommendation": "learn",
                                 "gap_level": "Minor Gap", "gap_severity": "Low"}],
    "recommended_screening_questions": [{"priority": "High", "category": "technical",
                                         "question": "q", "purpose": "p"}],
    "interview_recommendation": {"proceed": "Yes", "summary": "s",
                                 "key_strengths": ["k"], "concerns": []},
}


def is_valid(payload, schema):
    return jsonschema.Draft202012Validator(schema).is_valid(payload)


def mutate(payload, path, value=..., delete=False):
    p = copy.deepcopy(payload)
    node = p
    for key in path[:-1]:
        node = node[key]
    if delete:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return p


# --- schemas are themselves well-formed ----------------------------------

@pytest.mark.parametrize("schema", [candidate_schema, interviewer_schema], ids=["candidate", "interviewer"])
def test_schema_is_valid_json_schema(schema):
    jsonschema.Draft202012Validator.check_schema(schema)
    json.dumps(schema)  # must be serialisable to send to Gemini


def test_valid_candidate_payload_passes():
    assert is_valid(VALID_CANDIDATE, candidate_schema)


def test_valid_interviewer_payload_passes():
    assert is_valid(VALID_INTERVIEWER, interviewer_schema)


# --- candidate schema rejections -----------------------------------------

@pytest.mark.parametrize("path", [
    ("company",), ("role",), ("swot_analysis",), ("skill_assessment",),
    ("concept_refresh",), ("interview_questions",), ("company_insights",),
    ("swot_analysis", "threats"),
    ("skill_assessment", "match_percentage"),
    ("company_insights", "company_overview"),
])
def test_candidate_missing_required_field_fails(path):
    assert not is_valid(mutate(VALID_CANDIDATE, path, delete=True), candidate_schema)


@pytest.mark.parametrize("path,value", [
    (("skill_assessment", "match_percentage"), 150),
    (("skill_assessment", "match_percentage"), -1),
    (("skill_assessment", "match_percentage"), "72%"),
    (("interview_questions", 0, "category"), "Trivia"),
    (("interview_questions", 0, "difficulty"), "Impossible"),
    (("swot_analysis", "strengths"), "not a list"),
    (("company_insights", "culture_points"), [1, 2]),
])
def test_candidate_malformed_field_fails(path, value):
    assert not is_valid(mutate(VALID_CANDIDATE, path, value), candidate_schema)


def test_candidate_concept_refresh_requires_video_resource():
    # The effective item schema is the *second* "items" key (see xfail below);
    # the frontend (components/concept-refresh.tsx) reads video_resource.
    bad = mutate(VALID_CANDIDATE, ("concept_refresh", 0, "video_resource"), delete=True)
    assert not is_valid(bad, candidate_schema)
    assert candidate_schema["properties"]["concept_refresh"]["items"]["required"][-1] == "video_resource"


def _duplicate_dict_keys(source: str):
    dups = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            dups += [(node.lineno, k) for k in set(keys) if keys.count(k) > 1]
    return dups


@pytest.mark.xfail(strict=True, reason=(
    "BUG: candidate_schema.concept_refresh declares 'items' twice "
    "(backend/app/schemas/response.py:114 and :130); Python silently keeps the "
    "second, so the article_resource item schema is dead code."
))
def test_response_schemas_have_no_duplicate_keys():
    assert _duplicate_dict_keys(RESPONSE_PY.read_text(encoding="utf-8")) == []


# --- interviewer schema rejections ---------------------------------------

@pytest.mark.parametrize("path", [
    ("candidate_overview", "full_name"),
    ("compatibility_score", "overall_score"),
    ("skills_assessment", "data"),
    ("skills_assessment", "data", "skillsDistribution"),
    ("interview_recommendation", "proceed"),
])
def test_interviewer_missing_nested_required_field_fails(path):
    assert not is_valid(mutate(VALID_INTERVIEWER, path, delete=True), interviewer_schema)


@pytest.mark.parametrize("path,value", [
    (("compatibility_score", "overall_score"), 101),
    (("compatibility_score", "match"), "great"),
    (("skills_assessment", "data", "skillsByCategory", 0, "skills", 0, "level"), 6),
    (("skills_assessment", "data", "skillsByCategory", 0, "skills", 0, "status"), "ok"),
    (("experience", 0, "relevance_to_job"), "Very High"),
    (("skill_gaps_and_concerns", 0, "gap_level"), "Huge Gap"),
    (("interview_recommendation", "proceed"), "Maybe"),
])
def test_interviewer_malformed_field_fails(path, value):
    assert not is_valid(mutate(VALID_INTERVIEWER, path, value), interviewer_schema)


@pytest.mark.xfail(strict=True, reason=(
    "BUG: interviewer_schema has no top-level 'required' list "
    "(backend/app/schemas/response.py:201-364), so an LLM response missing whole "
    "sections (even {}) is schema-valid and the frontend components receive undefined."
))
def test_interviewer_schema_requires_top_level_sections():
    assert not is_valid({}, interviewer_schema)


# --- GeminiLLM: LLM text -> JSON -----------------------------------------

@pytest.fixture
def gemini(monkeypatch):
    from app.service.llm import gemini as gemini_mod
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    fake_client = MagicMock()
    monkeypatch.setattr(gemini_mod.genai, "Client", MagicMock(return_value=fake_client))
    llm = gemini_mod.GeminiLLM()
    return llm, fake_client


def _respond(client, text):
    client.models.generate_content.return_value = SimpleNamespace(text=text)


def test_gemini_requires_api_key(monkeypatch):
    from app.service.llm import gemini as gemini_mod
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        gemini_mod.GeminiLLM()


def test_gemini_generate_parses_json_and_sends_schema(gemini):
    llm, client = gemini
    _respond(client, json.dumps(VALID_INTERVIEWER))
    out = llm.generate("prompt", interviewer_schema)
    assert out == VALID_INTERVIEWER

    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-2.5-flash"
    assert kwargs["contents"] == "prompt"
    cfg = kwargs["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema is interviewer_schema


@pytest.mark.parametrize("text", ["not json", '{"company": "Acme"', ""])
def test_gemini_generate_raises_on_malformed_json(gemini, text):
    llm, client = gemini
    _respond(client, text)
    with pytest.raises(json.JSONDecodeError):
        llm.generate("p", candidate_schema)


def test_gemini_generate_raises_on_none_text(gemini):
    # e.g. safety block / MAX_TOKENS: response.text is None.
    llm, client = gemini
    _respond(client, None)
    with pytest.raises(TypeError):
        llm.generate("p", candidate_schema)


# --- get_interview_cheatsheet orchestration ------------------------------

@pytest.fixture
def cheatsheet(monkeypatch):
    from app.service import interview_cheatsheet as mod
    fake_llm = MagicMock()
    monkeypatch.setattr(mod, "GeminiLLM", MagicMock(return_value=fake_llm))
    return mod, fake_llm


def test_cheatsheet_selects_schema_by_type(cheatsheet):
    mod, llm = cheatsheet
    llm.generate.return_value = VALID_CANDIDATE
    assert mod.get_interview_cheatsheet("r", "jd", "candidate") == VALID_CANDIDATE
    assert llm.generate.call_args.args[1] is candidate_schema

    llm.generate.return_value = VALID_INTERVIEWER
    mod.get_interview_cheatsheet("r", "jd", "interviewer")
    assert llm.generate.call_args.args[1] is interviewer_schema


def test_cheatsheet_returns_none_when_llm_output_unparseable(cheatsheet):
    mod, llm = cheatsheet
    llm.generate.side_effect = json.JSONDecodeError("bad", "x", 0)
    assert mod.get_interview_cheatsheet("r", "jd", "candidate") is None


def test_cheatsheet_invalid_type_returns_none_without_calling_llm(cheatsheet):
    mod, llm = cheatsheet
    assert mod.get_interview_cheatsheet("r", "jd", "bogus") is None
    llm.generate.assert_not_called()


def test_cheatsheet_prompt_has_empty_rag_context(cheatsheet):
    # A fresh RAGEngine is built per call and nothing is ever indexed, so the
    # retrieval step always contributes nothing (documented gap, not xfail).
    mod, llm = cheatsheet
    llm.generate.return_value = VALID_CANDIDATE
    mod.get_interview_cheatsheet("RESUME_X", "JD_Y", "candidate")
    prompt = llm.generate.call_args.args[0]
    assert "RESUME_X" in prompt and "JD_Y" in prompt
    assert prompt.rstrip().endswith("ADDITIONAL CONTEXT:")


@pytest.mark.xfail(strict=True, reason=(
    "BUG: LLM output is never validated against the schema "
    "(backend/app/service/interview_cheatsheet.py:20, llm/gemini.py:31); a "
    "schema-violating response is persisted and returned to the client as-is."
))
def test_cheatsheet_rejects_schema_violating_llm_output(cheatsheet):
    mod, llm = cheatsheet
    llm.generate.return_value = {"company": "Acme"}  # missing every other section
    assert mod.get_interview_cheatsheet("r", "jd", "candidate") is None
