#!/usr/bin/env python3
"""
opencode-session-stats.py
Estrae statistiche di consumo token da sessioni OpenCode.

Modalità:
  - Senza argomenti: lista sessioni interattiva → seleziona → esporta e analizza
  - Con session ID:  opencode export <id> → analizza
  - Con file JSON:   analizza file già esportati
"""

import json
import re
import subprocess
import sys
import argparse
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class TokenStats:
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.reasoning

    def __add__(self, other: "TokenStats") -> "TokenStats":
        return TokenStats(
            input=self.input + other.input,
            output=self.output + other.output,
            reasoning=self.reasoning + other.reasoning,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
        )


@dataclass
class MessageStats:
    message_id: str
    role: str
    model_id: Optional[str]
    provider_id: Optional[str]
    tokens: TokenStats
    cost: float
    finish: Optional[str]


@dataclass
class SessionStats:
    session_id: str
    title: str
    agent: str
    model_id: str
    provider_id: str
    session_tokens: TokenStats
    session_cost: float
    messages: list[MessageStats] = field(default_factory=list)

    @property
    def message_count(self) -> dict:
        counts: dict[str, int] = {"user": 0, "assistant": 0, "total": 0}
        for m in self.messages:
            counts[m.role] = counts.get(m.role, 0) + 1
            counts["total"] += 1
        return counts


# ─── Parsing ─────────────────────────────────────────────────────────────────

def parse_tokens(raw: dict) -> TokenStats:
    cache = raw.get("cache", {})
    return TokenStats(
        input=raw.get("input", 0),
        output=raw.get("output", 0),
        reasoning=raw.get("reasoning", 0),
        cache_read=cache.get("read", 0),
        cache_write=cache.get("write", 0),
    )


def parse_session(data: dict) -> SessionStats:
    info = data.get("info", {})
    model = info.get("model", {})

    session = SessionStats(
        session_id=info.get("id", "unknown"),
        title=info.get("title", ""),
        agent=info.get("agent", ""),
        model_id=model.get("id", model.get("modelID", "")),
        provider_id=model.get("providerID", ""),
        session_tokens=parse_tokens(info.get("tokens", {})),
        session_cost=info.get("cost", 0.0),
    )

    for msg in data.get("messages", []):
        msg_info = msg.get("info", {})
        session.messages.append(MessageStats(
            message_id=msg_info.get("id", ""),
            role=msg_info.get("role", ""),
            model_id=msg_info.get("modelID"),
            provider_id=msg_info.get("providerID"),
            tokens=parse_tokens(msg_info.get("tokens", {})),
            cost=msg_info.get("cost", 0.0),
            finish=msg_info.get("finish"),
        ))

    return session


# ─── OpenCode integration ─────────────────────────────────────────────────────

@dataclass
class SessionListEntry:
    session_id: str
    title: str
    updated_raw: str


def fetch_session_list() -> list[SessionListEntry]:
    """Chiama `opencode session list` e parsa l'output tabellare."""
    try:
        result = subprocess.run(
            ["opencode", "session", "list"],
            capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        print("❌ opencode non trovato nel PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ opencode session list fallito: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    entries: list[SessionListEntry] = []
    for line in result.stdout.splitlines():
        # Salta header e separatori
        if line.startswith("Session ID") or line.startswith("─") or not line.strip():
            continue
        # Formato: ses_XXXX  <title>  <updated>
        # Colonne separate da 2+ spazi
        parts = re.split(r"\s{2,}", line.strip(), maxsplit=2)
        if len(parts) >= 1 and parts[0].startswith("ses_"):
            entries.append(SessionListEntry(
                session_id=parts[0],
                title=parts[1] if len(parts) > 1 else "",
                updated_raw=parts[2] if len(parts) > 2 else "",
            ))
    return entries


def interactive_select_session(entries: list[SessionListEntry]) -> str:
    """Mostra lista sessioni e chiede all'utente di selezionarne una."""
    print("\n📋 Sessioni OpenCode disponibili:\n")
    print(f"  {'#':>3}  {'Session ID':<35} {'Updated':<22} Title")
    print(f"  {'─'*3}  {'─'*35} {'─'*22} {'─'*40}")
    for i, e in enumerate(entries, 1):
        title = e.title[:55] + "…" if len(e.title) > 55 else e.title
        print(f"  {i:>3}  {e.session_id:<35} {e.updated_raw:<22} {title}")

    print()
    while True:
        raw = input("Inserisci numero, session ID (ses_...) o 'q' per uscire: ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            sys.exit(0)
        if raw.startswith("ses_"):
            return raw
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(entries):
                return entries[idx].session_id
        except ValueError:
            pass
        print("  ⚠️  Selezione non valida, riprova.")


def export_session(session_id: str) -> dict:
    """Esegue `opencode export <session_id>` e restituisce il JSON parsato."""
    print(f"\n⏳ Esportazione sessione {session_id}...", file=sys.stderr)
    try:
        result = subprocess.run(
            ["opencode", "export", session_id],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ opencode export fallito: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"❌ Output non è JSON valido: {e}", file=sys.stderr)
        sys.exit(1)


# ─── Reporting ───────────────────────────────────────────────────────────────

def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def print_session_report(session: SessionStats, verbose: bool = False) -> None:
    st = session.session_tokens
    mc = session.message_count

    print(f"\n{'='*70}")
    print(f"  SESSION : {session.session_id}")
    print(f"  Title   : {session.title or '(no title)'}")
    print(f"  Agent   : {session.agent}")
    print(f"  Model   : {session.model_id} ({session.provider_id})")
    print(f"{'='*70}")

    print(f"\n  📊 TOKEN SUMMARY")
    print(f"     Input       : {fmt(st.input):>12}")
    print(f"     Output      : {fmt(st.output):>12}")
    print(f"     Reasoning   : {fmt(st.reasoning):>12}")
    print(f"     Cache read  : {fmt(st.cache_read):>12}")
    print(f"     Cache write : {fmt(st.cache_write):>12}")
    print(f"     {'─'*25}")
    print(f"     TOTAL       : {fmt(st.total):>12}")
    print(f"     Cost        : ${session.session_cost:.6f}")

    print(f"\n  💬 MESSAGES")
    print(f"     User        : {mc.get('user', 0):>4}")
    print(f"     Assistant   : {mc.get('assistant', 0):>4}")
    print(f"     Total       : {mc.get('total', 0):>4}")

    if verbose and session.messages:
        print(f"\n  📋 PER-MESSAGE BREAKDOWN (assistant only)")
        print(f"     {'ID (suffix)':<25} {'Model':<20} {'Input':>8} {'Output':>8} {'Total':>8}")
        print(f"     {'─'*25} {'─'*20} {'─'*8} {'─'*8} {'─'*8}")
        for m in session.messages:
            if m.role == "assistant" and m.tokens.total > 0:
                mid = "…" + m.message_id[-22:] if len(m.message_id) > 22 else m.message_id
                model = (m.model_id or "")[:18]
                print(f"     {mid:<25} {model:<20} {fmt(m.tokens.input):>8} {fmt(m.tokens.output):>8} {fmt(m.tokens.total):>8}")


def print_aggregate(sessions: list[SessionStats]) -> None:
    if len(sessions) <= 1:
        return

    total = TokenStats()
    total_cost = 0.0
    models: dict[str, int] = {}

    for s in sessions:
        total = total + s.session_tokens
        total_cost += s.session_cost
        key = f"{s.model_id} ({s.provider_id})"
        models[key] = models.get(key, 0) + 1

    print(f"\n{'='*70}")
    print(f"  📈 AGGREGATE — {len(sessions)} sessioni")
    print(f"{'='*70}")
    print(f"     Input       : {fmt(total.input):>12}")
    print(f"     Output      : {fmt(total.output):>12}")
    print(f"     Reasoning   : {fmt(total.reasoning):>12}")
    print(f"     Cache read  : {fmt(total.cache_read):>12}")
    print(f"     Cache write : {fmt(total.cache_write):>12}")
    print(f"     {'─'*25}")
    print(f"     TOTAL       : {fmt(total.total):>12}")
    print(f"     Cost        : ${total_cost:.6f}")
    print(f"\n  Modelli usati:")
    for model, count in sorted(models.items(), key=lambda x: -x[1]):
        print(f"     {count:>3}x  {model}")


def output_json(sessions: list[SessionStats]) -> None:
    out = []
    for s in sessions:
        st = s.session_tokens
        out.append({
            "session_id": s.session_id,
            "title": s.title,
            "agent": s.agent,
            "model": s.model_id,
            "provider": s.provider_id,
            "tokens": {
                "input": st.input,
                "output": st.output,
                "reasoning": st.reasoning,
                "cache_read": st.cache_read,
                "cache_write": st.cache_write,
                "total": st.total,
            },
            "cost": s.session_cost,
            "messages": s.message_count,
        })
    print(json.dumps(out, indent=2, ensure_ascii=False))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Statistiche token sessioni OpenCode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python opencode-session-stats.py                    # interattivo: lista + selezione
  python opencode-session-stats.py ses_abc123         # export diretto per ID
  python opencode-session-stats.py export.json        # analizza file già esportato
  python opencode-session-stats.py *.json -v          # più file, breakdown per messaggio
  python opencode-session-stats.py ses_abc123 --json  # output JSON
        """,
    )
    parser.add_argument(
        "targets", nargs="*",
        help="Session ID (ses_...) o file JSON. Se omesso: modalità interattiva."
    )
    parser.add_argument("--dir", "-d", help="Directory da scansionare per file .json")
    parser.add_argument("--verbose", "-v", action="store_true", help="Breakdown per messaggio")
    parser.add_argument("--json", "-j", action="store_true", help="Output in formato JSON")
    args = parser.parse_args()

    sessions: list[SessionStats] = []

    # ── Modalità interattiva (nessun argomento) ──
    if not args.targets and not args.dir:
        entries = fetch_session_list()
        if not entries:
            print("Nessuna sessione trovata.", file=sys.stderr)
            sys.exit(1)
        session_id = interactive_select_session(entries)
        data = export_session(session_id)
        sessions.append(parse_session(data))

    else:
        # ── Directory scan ──
        if args.dir:
            for p in sorted(Path(args.dir).glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        sessions.append(parse_session(item))
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"⚠️  {p}: {e}", file=sys.stderr)

        # ── Targets: session ID o file ──
        for target in args.targets:
            if target.startswith("ses_"):
                data = export_session(target)
                sessions.append(parse_session(data))
            else:
                p = Path(target)
                if p.is_dir():
                    for fp in sorted(p.glob("*.json")):
                        try:
                            data = json.loads(fp.read_text(encoding="utf-8"))
                            items = data if isinstance(data, list) else [data]
                            for item in items:
                                sessions.append(parse_session(item))
                        except (json.JSONDecodeError, KeyError) as e:
                            print(f"⚠️  {fp}: {e}", file=sys.stderr)
                else:
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            sessions.append(parse_session(item))
                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"⚠️  {p}: {e}", file=sys.stderr)

    if not sessions:
        print("Nessuna sessione valida trovata.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        output_json(sessions)
        return

    for session in sessions:
        print_session_report(session, verbose=args.verbose)

    print_aggregate(sessions)
    print()


if __name__ == "__main__":
    main()
