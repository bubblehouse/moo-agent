"""
krustylu lore source for moo-agent world-builders.

``LoreClient`` wraps a streamable-HTTP MCP session to the krustylu Simpsons
archive and turns a location or character into a compact, build-ready text
brief — a condensed wiki summary plus the precise detail that lives in the
script lines (stage directions, signature dialogue, the characters who haunt a
place). Builders consume the brief through the ``lore_room``/``lore_character``
tools; the model never sees krustylu's raw query schema.

Every public method is defensive: a miss, a malformed query, or an unreachable
server yields an empty-but-usable string, never an exception into the LLM cycle.
The curation itself lives in module-level pure functions so it can be unit
tested against captured query results without a live server.
"""

import asyncio
import logging
import re
from contextlib import AsyncExitStack

log = logging.getLogger(__name__)

# [text](url) and [text](url "title") -> text
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
# A markdown section heading line, e.g. "## Profile".
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
# Quote characters that break krustylu's full-text query parser ("No closing
# quotation"). Simpsons names are full of apostrophes (Moe's, Krusty's).
_QUOTE_RE = re.compile(r"[\"']")


def sanitize_query(q: str) -> str:
    """Strip quote characters that the krustylu FTS parser chokes on."""
    return re.sub(r"\s+", " ", _QUOTE_RE.sub(" ", q or "")).strip()


def strip_md_links(text: str) -> str:
    """Replace ``[label](target)`` markdown links with their bare label."""
    return _LINK_RE.sub(r"\1", text or "")


def condense_description(markdown: str, max_chars: int) -> str:
    """
    Reduce a krustylu wiki ``description`` to a short plain-text summary.

    Keeps the intro prose up to the first section heading, strips markdown
    links, collapses whitespace, and truncates at ``max_chars`` on a sentence
    boundary where possible.
    """
    if not markdown:
        return ""
    intro = _HEADING_RE.split(markdown, maxsplit=1)[0]
    text = strip_md_links(intro)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    cut = clipped.rfind(". ")
    if cut >= max_chars // 2:
        return clipped[: cut + 1]
    return clipped.rstrip() + "…"


def top_speaker_ids(group_rows: list, limit: int) -> list:
    """
    Sort a ``$group`` count result by frequency and return the top character
    ids. krustylu projects the group key back onto the grouped field name, so
    rows look like ``{"character_id": 17, "n": 1181}``.
    """
    rows = [r for r in (group_rows or []) if r.get("character_id") is not None]
    rows.sort(key=lambda r: r.get("n", 0), reverse=True)
    return [r["character_id"] for r in rows[:limit]]


# Per-line cap on quoted dialogue. Signature lines run long; this keeps a brief
# flavorful without letting one rant dominate the prompt's token budget.
_MAX_LINE_CHARS = 200


def _clean_line(text: str, limit: int = 0) -> str:
    """Collapse whitespace in a single script line, trim, optionally truncate."""
    line = re.sub(r"\s+", " ", (text or "")).strip()
    if limit and len(line) > limit:
        return line[:limit].rstrip() + "…"
    return line


def build_room_brief(
    location: dict,
    description: str,
    stage_lines: list,
    spoken_lines: list,
    npc_names: list,
    *,
    max_lines: int,
    max_chars: int,
) -> str:
    """
    Assemble the bounded room brief from raw krustylu rows. Pure function: all
    inputs are plain dicts/lists, so this is exercised directly in tests.
    """
    slug = location.get("slug", "")
    name = location.get("name", "Unknown")
    parts = [f"SOURCE: {name} (location:{slug})"]

    summary = condense_description(description, max_chars)
    if summary:
        parts.append(f"\nSUMMARY\n{summary}")

    settings = [_clean_line(r.get("raw_text", "")) for r in stage_lines[:max_lines]]
    settings = [s for s in settings if s]
    if settings:
        parts.append("\nSETTING (from script stage directions)\n" + "\n".join(f"- {s}" for s in settings))

    dialogue = [_clean_line(r.get("spoken_words", ""), _MAX_LINE_CHARS) for r in spoken_lines[:max_lines]]
    dialogue = [d for d in dialogue if d]
    if dialogue:
        parts.append("\nDIALOGUE (signature lines heard here)\n" + "\n".join(f'- "{d}"' for d in dialogue))

    if npc_names:
        parts.append("\nREGULARS (candidates for NPCs)\n" + ", ".join(npc_names))

    return "\n".join(parts)


def build_character_brief(
    character: dict,
    description: str,
    spoken_lines: list,
    *,
    max_lines: int,
    max_chars: int,
) -> str:
    """Assemble the bounded character brief from raw krustylu rows. Pure."""
    slug = character.get("slug", "")
    name = character.get("display_name") or character.get("name", "Unknown")
    gender = character.get("gender", "")
    header = f"SOURCE: {name} (character:{slug})"
    if gender:
        header += f" [{gender}]"
    parts = [header]

    summary = condense_description(description, max_chars)
    if summary:
        parts.append(f"\nSUMMARY\n{summary}")

    dialogue = [_clean_line(r.get("spoken_words", ""), _MAX_LINE_CHARS) for r in spoken_lines[:max_lines]]
    dialogue = [d for d in dialogue if d]
    if dialogue:
        parts.append("\nSIGNATURE LINES\n" + "\n".join(f'- "{d}"' for d in dialogue))

    return "\n".join(parts)


class LoreClient:
    """
    A persistent streamable-HTTP MCP client to the krustylu archive.

    Open it once at agent start (``await client.open()`` or ``async with``) and
    close it on shutdown. ``room_brief``/``character_brief`` each fire a handful
    of read-only queries and fold the results into a bounded brief.
    """

    def __init__(self, endpoint: str, *, verify_tls: bool = False, max_lines: int = 4, max_chars: int = 600):
        self._endpoint = endpoint
        self._verify_tls = verify_tls
        self._max_lines = max_lines
        self._max_chars = max_chars
        self._server = None
        self._stack: AsyncExitStack | None = None

    async def open(self) -> None:
        """Start the MCP session. Idempotent; logs and degrades on failure."""
        if self._server is not None:
            return
        from pydantic_ai.mcp import MCPToolset  # pylint: disable=import-outside-toplevel

        stack = AsyncExitStack()
        try:
            server = MCPToolset(self._endpoint, verify=self._verify_tls)
            await stack.enter_async_context(server)
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.warning("LoreClient could not connect to %s: %s", self._endpoint, e)
            await stack.aclose()
            return
        self._stack = stack
        self._server = server

    async def close(self) -> None:
        """Tear down the MCP session."""
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._server = None

    async def __aenter__(self) -> "LoreClient":
        await self.open()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def _call_tool(self, name: str, args: dict):
        """
        ``direct_call_tool`` with bounded backoff on a 429 rate-limit.

        krustylu's nginx caps request rate; under a burst of lore lookups the
        server answers 429. Without a retry that surfaces as an empty brief,
        which a builder reads as "no source found" and silently stops grounding
        its work. Three attempts with a doubling delay smooth over the cap.
        """
        delay = 0.5
        for attempt in range(3):
            try:
                return await self._server.direct_call_tool(name, args)
            except Exception as e:  # pylint: disable=broad-exception-caught
                status = getattr(getattr(e, "response", None), "status_code", None)
                if (status == 429 or "429" in str(e)) and attempt < 2:
                    log.warning("krustylu rate-limited (429); retrying in %.1fs", delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise

    async def _query(self, collection: str, pipeline: list) -> list:
        """Run a query_data_collections pipeline; return [] on any failure."""
        if self._server is None:
            return []
        try:
            result = await self._call_tool(
                "query_data_collections", {"collection": collection, "search_pipeline": pipeline}
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.warning("krustylu query on %s failed: %s", collection, e)
            return []
        return result if isinstance(result, list) else []

    async def _resolve(self, collection: str, name: str) -> dict | None:
        """
        Resolve a free-text name to a single canonical row using krustylu's
        full-text ``search`` (relevance-ranked), preferring canonical entries.
        """
        query = sanitize_query(name)
        if self._server is None or not query:
            return None
        try:
            envelope = await self._call_tool("search", {"q": query, "types": collection, "limit": 5})
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.warning("krustylu search for %r failed: %s", name, e)
            return None
        rows = (envelope or {}).get("results", {}).get(collection, []) if isinstance(envelope, dict) else []
        if not rows:
            return None
        for row in rows:
            if row.get("canonical") is None:
                return row
        return rows[0]

    async def source_exists(self, token: str) -> bool:
        """
        Confirm a ``type:slug`` source token resolves to a real krustylu row.

        Used to reject fabricated provenance tags (e.g. ``location:the-lab``)
        before they are written. A miss, malformed token, or dead server all
        return ``False`` — the caller decides how to coach the agent.
        """
        kind, _, slug = (token or "").partition(":")
        collection = {"location": "location", "character": "character"}.get(kind.strip())
        slug = slug.strip()
        if self._server is None or not collection or not slug:
            return False
        rows = await self._query(collection, [{"$match": {"slug": slug}}, {"$project": {"id": 1}}, {"$limit": 1}])
        return bool(rows)

    async def room_brief(self, name: str) -> str:
        """Build a bounded room brief for a krustylu location, or "" on a miss."""
        loc = await self._resolve("location", name)
        if not loc:
            return ""
        loc_id = loc.get("id")
        detail = await self._query("location", [{"$match": {"id": loc_id}}, {"$project": {"description": 1}}])
        description = detail[0].get("description", "") if detail else ""

        stage_lines = await self._query(
            "scriptline",
            [
                {"$match": {"location_id": loc_id, "speaking_line": False}},
                {"$project": {"raw_text": 1}},
                {"$limit": self._max_lines},
            ],
        )
        spoken_lines = await self._query(
            "scriptline",
            [
                {"$match": {"location_id": loc_id, "speaking_line": True}},
                {"$sort": {"word_count": -1}},
                {"$project": {"spoken_words": 1}},
                {"$limit": self._max_lines},
            ],
        )
        # $group must be the final stage, so sort/limit the counts client-side.
        groups = await self._query(
            "scriptline",
            [
                {"$match": {"location_id": loc_id, "speaking_line": True, "character_id": {"$ne": None}}},
                {"$group": {"_id": "$character_id", "n": {"$sum": 1}}},
            ],
        )
        npc_names = await self._names_for(top_speaker_ids(groups, self._max_lines))

        return build_room_brief(
            loc,
            description,
            stage_lines,
            spoken_lines,
            npc_names,
            max_lines=self._max_lines,
            max_chars=self._max_chars,
        )

    async def character_brief(self, name: str) -> str:
        """Build a bounded character brief, or "" on a miss."""
        char = await self._resolve("character", name)
        if not char:
            return ""
        char_id = char.get("id")
        detail = await self._query(
            "character",
            [{"$match": {"id": char_id}}, {"$project": {"description": 1, "gender": 1, "display_name": 1}}],
        )
        if detail:
            char = {**char, **detail[0]}
        description = char.get("description", "")

        spoken_lines = await self._query(
            "scriptline",
            [
                {"$match": {"character_id": char_id, "speaking_line": True}},
                {"$sort": {"word_count": -1}},
                {"$project": {"spoken_words": 1}},
                {"$limit": self._max_lines},
            ],
        )
        return build_character_brief(
            char, description, spoken_lines, max_lines=self._max_lines, max_chars=self._max_chars
        )

    async def _names_for(self, char_ids: list) -> list:
        """Resolve character ids to display names, preserving the input order."""
        if not char_ids:
            return []
        rows = await self._query(
            "character",
            [{"$match": {"id": {"$in": char_ids}}}, {"$project": {"id": 1, "display_name": 1, "name": 1}}],
        )
        by_id = {r.get("id"): (r.get("display_name") or r.get("name", "")) for r in rows}
        return [by_id[cid] for cid in char_ids if by_id.get(cid)]
