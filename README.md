# opencode-session-stats

Script Python per estrarre statistiche di consumo token dalle sessioni OpenCode.

## Requisiti

- Python 3.10+
- `opencode` CLI nel PATH e autenticato (per modalità interattiva e per session ID)
- Nessuna dipendenza esterna — stdlib pura

---

## Utilizzo

### Modalità interattiva (zero argomenti)

```bash
python opencode-session-stats.py
```

Chiama `opencode session list`, mostra la lista delle sessioni e chiede di selezionarne una per numero o ID. Poi esegue `opencode export <id>` e stampa le statistiche.

```
📋 Sessioni OpenCode disponibili:

    #  Session ID                          Updated                Title
  ───  ─────────────────────────────────── ──────────────────── ────────────────────────────────────────
    1  ses_192251yraaaffeUasrrd1kZtcR      19:55 AM             Estrazione statistiche consumo token…
    2  ses_195e3180fffe6iGtpcKUxFJcSc      18:33 AM             Creare uno script python per elaborare…
    ...

Inserisci numero, session ID (ses_...) o 'q' per uscire: 2
```

---

### Per session ID diretto

```bash
python opencode-session-stats.py ses_192251yraaaffeUasrrd1kZtcR
```

Esegue `opencode export <id>` e analizza il risultato. Nessun file intermedio.

---

### Da file JSON già esportato

```bash
# File singolo
python opencode-session-stats.py export.json

# Più file (aggregato automatico)
python opencode-session-stats.py *.json

# Directory intera
python opencode-session-stats.py --dir ./exports/
```

---

## Opzioni

| Flag | Alias | Descrizione |
|------|-------|-------------|
| `--verbose` | `-v` | Breakdown token per singolo messaggio assistant |
| `--json` | `-j` | Output in formato JSON (per pipeline/jq) |
| `--dir PATH` | `-d` | Scansiona directory per file `.json` |

---

## Output di esempio

```
======================================================================
  SESSION : ses_192251yraaaffeUasrrd1kZtcR
  Title   : Creazione script per calcolo sessione
  Agent   : conversational-gpt-5.5
  Model   : gpt-5-mini (github-copilot)
======================================================================

  📊 TOKEN SUMMARY
     Input       :       93.382
     Output      :        4.352
     Reasoning   :            0
     Cache read  :       29.312
     Cache write :            0
     ─────────────────────────
     TOTAL       :       97.734
     Cost        : $0.000000

  💬 MESSAGES
     User        :    2
     Assistant   :    4
     Total       :    6
```

Con `-v` aggiunge il breakdown per messaggio:

```
  📋 PER-MESSAGE BREAKDOWN (assistant only)
     ID (suffix)               Model                   Input   Output    Total
     ───────────────────────── ──────────────────── ──────── ──────── ────────
     …ce823001su69pyeZXT0iPS   gpt-5-mini             28.350    1.305   29.655
     …369370018gCdYIwXRAhtB1   gpt-5-mini             29.868    1.526   31.394
```

Con più sessioni aggiunge un blocco aggregato finale:

```
======================================================================
  📈 AGGREGATE — 3 sessioni
======================================================================
     Input       :      250.000
     Output      :       12.000
     ...
     TOTAL       :      262.000

  Modelli usati:
    3x  gpt-5-mini (github-copilot)
```

---

## Output JSON (`--json`)

```bash
python opencode-session-stats.py ses_abc123 --json | jq '.[] | .tokens.total'
```

Struttura per sessione:

```json
{
  "session_id": "ses_...",
  "title": "...",
  "agent": "...",
  "model": "gpt-5-mini",
  "provider": "github-copilot",
  "tokens": {
    "input": 93382,
    "output": 4352,
    "reasoning": 0,
    "cache_read": 29312,
    "cache_write": 0,
    "total": 97734
  },
  "cost": 0.0,
  "messages": { "user": 2, "assistant": 4, "total": 6 }
}
```

---

## Fonti dati

| Campo | Fonte nel JSON |
|-------|---------------|
| Token totali sessione | `info.tokens` |
| Cache read/write | `info.tokens.cache` |
| Cost | `info.cost` |
| Breakdown per messaggio | `messages[].info.tokens` |
| Modello/provider | `info.model` |

