"""
Tests for moo/agent/lore.py.

The curation is pure functions exercised directly; ``LoreClient`` is driven by a
fake MCP server so the assembly, canonical preference, and graceful-failure
paths are covered without a live krustylu endpoint. No DJANGO_SETTINGS_MODULE.
"""

import asyncio

# pylint: disable=protected-access  # Tests drive LoreClient's internals against a fake MCP server.

from moo.agent.lore import (
    LoreClient,
    build_character_brief,
    build_room_brief,
    condense_description,
    sanitize_query,
    strip_md_links,
    top_speaker_ids,
)


def test_strip_md_links_plain_and_titled():
    """strip_md_links reduces [label](url) and [label](url "title") to the label."""
    assert strip_md_links('see [Moe](/c/moe/ "Moe") and [Bart](/b)') == "see Moe and Bart"


def test_condense_description_cuts_at_heading_and_strips_links():
    """condense_description keeps the intro, drops links, and stops at the first heading."""
    md = "**Moe's** is a [bar](/x) in town.\n\n## Profile\nfloors and stuff"
    out = condense_description(md, max_chars=600)
    assert out == "**Moe's** is a bar in town."
    assert "Profile" not in out


def test_condense_description_truncates_on_sentence_boundary():
    """A long description is clipped near max_chars, preferring a sentence end."""
    md = "One sentence here. " + ("filler " * 200)
    out = condense_description(md, max_chars=40)
    assert len(out) <= 41
    assert out.endswith(".") or out.endswith("…")


def test_condense_description_empty():
    """An empty description condenses to an empty string."""
    assert condense_description("", max_chars=600) == ""


def test_sanitize_query_removes_quotes():
    """sanitize_query strips the quote chars that break krustylu's FTS parser."""
    assert sanitize_query("Moe's Tavern") == "Moe s Tavern"
    assert sanitize_query('a "quoted" name') == "a quoted name"


def test_top_speaker_ids_sorts_and_drops_null():
    """top_speaker_ids ranks by count, drops null character ids, and honors the limit."""
    rows = [
        {"character_id": 2, "n": 988},
        {"character_id": None, "n": 9999},
        {"character_id": 17, "n": 1181},
        {"character_id": 18, "n": 207},
    ]
    assert top_speaker_ids(rows, limit=2) == [17, 2]


def test_build_room_brief_sections_and_line_cap():
    """build_room_brief renders all sections and truncates an over-long dialogue line."""
    loc = {"name": "Moe's Tavern", "slug": "moe-tavern"}
    long_line = "blah " * 100
    brief = build_room_brief(
        loc,
        "**Moe's** is a [bar](/x) in Springfield.",
        [{"raw_text": "(Moe's Tavern: int. night)"}],
        [{"spoken_words": long_line}],
        ["Moe", "Homer"],
        max_lines=4,
        max_chars=600,
    )
    assert "SOURCE: Moe's Tavern (location:moe-tavern)" in brief
    assert "bar in Springfield" in brief  # link stripped
    assert "SETTING" in brief and "int. night" in brief
    assert "REGULARS" in brief and "Moe, Homer" in brief
    assert "…" in brief  # the long dialogue line was capped


def test_build_room_brief_omits_empty_sections():
    """Sections with no data are omitted rather than rendered empty."""
    brief = build_room_brief({"name": "Void", "slug": "void"}, "", [], [], [], max_lines=4, max_chars=600)
    assert brief == "SOURCE: Void (location:void)"


def test_build_character_brief_header_and_gender():
    """build_character_brief prefers display_name and shows gender plus the slug token."""
    brief = build_character_brief(
        {"display_name": "Moe", "name": "Moe Szyslak", "slug": "moe-szyslak", "gender": "m"},
        "A [bartender](/x).",
        [{"spoken_words": "What'll it be?"}],
        max_lines=4,
        max_chars=600,
    )
    assert brief.startswith("SOURCE: Moe (character:moe-szyslak) [m]")
    assert "bartender" in brief
    assert "SIGNATURE LINES" in brief and "What'll it be?" in brief


class _FakeServer:
    """Minimal stand-in for MCPToolset.direct_call_tool over canned krustylu data."""

    def __init__(self, *, search=None, raises=False):
        self._search = search or {}
        self._raises = raises

    async def direct_call_tool(self, name, args, metadata=None):
        if self._raises:
            raise RuntimeError("boom")
        if name == "search":
            return {"results": {args["types"]: self._search.get(args["types"], [])}}
        collection = args["collection"]
        pipeline = args["search_pipeline"]
        match = next((s["$match"] for s in pipeline if "$match" in s), {})
        if collection == "location":
            return [{"description": "**Moe's** is a [bar](/x) in Springfield."}]
        if collection == "character":
            if isinstance(match.get("id"), dict):  # $in -> name resolution
                return [{"id": 17, "display_name": "Moe"}, {"id": 2, "display_name": "Homer"}]
            return [{"description": "A bartender.", "gender": "m", "display_name": "Moe"}]
        if collection == "scriptline":
            if any("$group" in s for s in pipeline):
                return [{"character_id": 17, "n": 1181}, {"character_id": 2, "n": 988}]
            if match.get("speaking_line") is False:
                return [{"raw_text": "(Moe's Tavern: int. night)"}]
            return [{"spoken_words": "Phone call for Al, Al Caholic."}]
        return []


def _run(coro):
    return asyncio.run(coro)


def test_room_brief_full_assembly():
    """LoreClient.room_brief resolves a location and folds the queries into a brief."""
    client = LoreClient("http://x", max_lines=4, max_chars=600)
    client._server = _FakeServer(
        search={"location": [{"id": 15, "name": "Moe's Tavern", "slug": "moe-tavern", "canonical": None}]}
    )
    brief = _run(client.room_brief("Moe's Tavern"))
    assert "SOURCE: Moe's Tavern (location:moe-tavern)" in brief
    assert "bar in Springfield" in brief
    assert "Al, Al Caholic" in brief
    assert "Moe, Homer" in brief


def test_resolve_prefers_canonical():
    """_resolve picks the canonical row even when a variant ranks first."""
    client = LoreClient("http://x")
    client._server = _FakeServer(
        search={
            "location": [
                {"id": 99, "name": "Moe's (variant)", "slug": "moe-v", "canonical": 15},
                {"id": 15, "name": "Moe's Tavern", "slug": "moe-tavern", "canonical": None},
            ]
        }
    )
    row = _run(client._resolve("location", "Moe's"))
    assert row["id"] == 15


def test_room_brief_miss_returns_empty():
    """A location that resolves to nothing yields an empty string, not an error."""
    client = LoreClient("http://x")
    client._server = _FakeServer(search={"location": []})
    assert _run(client.room_brief("Nowhere")) == ""


def test_queries_degrade_when_server_unset():
    """With no open session, lookups return empty without raising."""
    client = LoreClient("http://x")
    assert _run(client.room_brief("Moe's Tavern")) == ""
    assert _run(client._query("location", [])) == []
    assert _run(client._resolve("location", "Moe's")) is None


def test_query_swallows_server_errors():
    """A raising MCP call is caught and reported as an empty result."""
    client = LoreClient("http://x")
    client._server = _FakeServer(raises=True)
    assert _run(client._query("scriptline", [{"$match": {}}])) == []
    assert _run(client.room_brief("Moe's Tavern")) == ""
