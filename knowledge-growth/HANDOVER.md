# Knowledge Growth Daily Reporter - Handover

**Date**: 2026-04-23
**Context**: Sync-based contributor attribution hit a wall. Need an engineer familiar with Obsidian internals to take over.

---

## What We Are Building

A daily knowledge growth reporter that scans an Obsidian vault, attributes files to contributors, and generates a Markdown report.

**Vault path**: `C:\Users\ryshi\Documents\AIC-000`
**Contributors**: Rosettaguo, veil
**Project**: `C:\Hello-World\knowledge-growth`

---

## Core Problem: Contributor Attribution

We need to know who wrote/modified each markdown file. Current fallback chain:

1. frontmatter `author` field (only 14 files have this)
2. Obsidian Sync device map (IDEAL but currently broken)
3. Path keyword matching (fallback)
4. "unknown"

---

## Attempt 1: Obsidian Sync getHistory()

**Plugin**: `C:\Users\ryshi\Documents\AIC-000\.obsidian\plugins\sync-history-exporter/`

API used:
```js
app.internalPlugins.plugins.sync.instance.getHistory(file.path)
```

**Expected return**: `[{device, ts, size, uid}]`

**Actual return**: `[]` for ALL files

**Sync instance state**:
```js
{
  deviceName: null,
  userId: -1,
  initialized: false,
  ready: false,
  vaultId: null,
  vaultName: null
}
```

**User claims**: Has active Sync subscription, logged in, can see version history in Obsidian UI.

**Tried**:
- Delay 3s after plugin load -> no change
- Poll for 60s waiting for `initialized=true && ready=true` -> never happens
- Full Obsidian restart -> still `initialized=false`

**Open questions**:
- Does Sync init happen AFTER community plugins load?
- Is version history server-side only?
- Is the "version history" user sees actually File Recovery, not Sync?
- Does `instance.setup()` or `instance.init()` need to be called?

---

## Attempt 2: File Recovery DB

API:
```js
app.internalPlugins.plugins['file-recovery'].instance.db
  .transaction('backups').store.getAll()
```

**Result**: 787 backups, 431 unique files.

**Fields**: `{path, ts, data}` — **NO device/author info**.

Cannot be used for attribution.

---

## Attempt 3: MetadataCache frontmatter

Scanned ALL markdown files. Only **14 files** have `author` in frontmatter.

Coverage: ~1%. Not viable.

---

## Folder Patterns (Observable Ownership)

| Pattern | Owner |
|---------|-------|
| `1 Veil's Playground` | veil |
| `2 Rosetta's Playground` | Rosettaguo |
| `T-B Openclaw/Rosetta水产养殖` | Rosettaguo |
| `T-B 官网/.../Rosetta又开始想了` | Rosettaguo |
| `录音/会议纪要/` | Mixed |

---

## What We Need From The Next Engineer

1. **Figure out why Sync instance is not initialized** (`initialized=false` after 60s)
2. **If Sync works**: Extract device map, build `DEVICE_MAP` in `.env`
3. **If Sync is a dead end**: Decide whether folder-based rules are acceptable, or explore:
   - Git init the vault (git log gives authors for free)
   - Frontmatter convention enforcement
   - Other Obsidian plugins that track edits

---

## Environment

- OS: Windows 11
- Obsidian: unknown version (ask user)
- Sync: user claims active subscription
- Vault: ~2000+ markdown files
- PowerShell default encoding: GBK (causes `UnicodeEncodeError` on emoji output)

---

## Files

- `scanner.py` - File scanner with contributor guessing logic
- `reporter.py` - Markdown report generator
- `vault_writer.py` - Writes reports back to Obsidian
- `config.py` - Config (vault path, contributor rules, LLM keys)
- `main.py` - CLI entry point
- `state.json` - Last scan timestamp
- `.obsidian/plugins/sync-history-exporter/` - Obsidian plugin (manifest.json + main.js)
