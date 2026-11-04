"""Deterministic build-idea suggestions from REAL static analysis.

No model calls. Every card cites actual exports found in the pasted repos
by repofuse.analyze. Cards are labeled in the UI as derived from local
static analysis, not AI-generated. If the repos don't match a known
complementary pattern, the fallback card says the analysis is shallow and
a model would do better - honesty over coverage.
"""

_CAPABILITY_EXPORTS = {
    "web":       {"Microdot", "Flask", "FastAPI", "Request", "Response",
                  "HTTPException", "route", "Bottle", "Sanic"},
    "realtime":  {"WebSocket", "SSE", "ServerSentEvents"},
    "orm":       {"Model", "Database", "SqliteDatabase", "PostgresqlDatabase",
                  "MySQLDatabase", "CharField", "IntegerField",
                  "ForeignKeyField", "ModelSelect"},
    "auth":      {"BasicAuth", "TokenAuth", "Auth", "HTTPAuth"},
    "templates": {"Template", "render_template", "Jinja2", "Environment"},
    "cli":       {"argparse", "ArgumentParser", "click", "Typer", "Command"},
    "httpclient": {"requests", "Client", "Session", "httpx"},
    "validate":  {"validate_note_payload", "Schema", "Validator", "validate"},
}


def _caps(export_names):
    names = set(export_names)
    return {cap for cap, markers in _CAPABILITY_EXPORTS.items()
            if names & markers}


def _cite(meta, markers, n=3):
    found = [e for e in meta.get("analysis", {}).get("exports", [])
             if e in markers]
    return found[:n]


def suggest(metas):
    """metas: {slug: ingest-meta dict including ['analysis']['exports']}.
    Returns up to 3 cards: id, title, what, fit (actual exports), repos."""
    slugs = list(metas)
    if len(slugs) < 2:
        return []
    a, b = slugs[0], slugs[1]
    ea = set(metas[a].get("analysis", {}).get("exports", []))
    eb = set(metas[b].get("analysis", {}).get("exports", []))
    ca, cb = _caps(ea), _caps(eb)
    cards = []

    web = a if "web" in ca else (b if "web" in cb else None)
    orm = a if "orm" in ca else (b if "orm" in cb else None)

    if web and orm and web != orm:
        wm, om = metas[web], metas[orm]
        fit = (_cite(wm, _CAPABILITY_EXPORTS["web"], 2)
               + _cite(om, _CAPABILITY_EXPORTS["orm"], 2))
        cards.append({
            "id": "notes-crud",
            "title": "Tiny notes API",
            "what": "REST endpoints to create, list, read and edit notes, "
                    "stored in a real database file.",
            "fit": fit,
            "repos": [web, orm],
        })
        cards.append({
            "id": "inventory-crud",
            "title": "Inventory tracker API",
            "what": "Same skeleton as the notes API but for tracking items "
                    "with quantities - add, list, update, remove.",
            "fit": fit,
            "repos": [web, orm],
        })
        if ("auth" in (_caps(ea) | _caps(eb))):
            am = metas[web]
            cards.append({
                "id": "auth-api",
                "title": "Notes API with token-auth sketch",
                "what": "The notes API plus a first pass at token-based "
                        "access, wired from the auth exports. A starting "
                        "point to explore - NOT working or reviewed "
                        "security.",
                "fit": fit + _cite(am, _CAPABILITY_EXPORTS["auth"], 1),
                "repos": [web, orm],
            })
    if not cards and web and "realtime" in (_caps(ea) | _caps(eb)):
        other = b if web == a else a
        cards.append({
            "id": "live-feed",
            "title": "Live-updating feed",
            "what": "A page that updates in real time over a websocket "
                    "or server-sent events.",
            "fit": _cite(metas[web], _CAPABILITY_EXPORTS["web"], 2)
                   + _cite(metas[web], _CAPABILITY_EXPORTS["realtime"], 1),
            "repos": [web, other],
        })
    if not cards:
        cards.append({
            "id": "generic-glue",
            "title": f"{a} + {b} glue layer",
            "what": "A thin wrapper connecting the two libraries. "
                    "Static analysis is shallow here - a model call would "
                    "propose sharper ideas.",
            "fit": sorted(ea)[:2] + sorted(eb)[:2],
            "repos": [a, b],
        })
    return cards[:3]
