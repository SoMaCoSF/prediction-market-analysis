<!-- =============================================================================== file_id: SOM-DOC-0901-v1.0.0 name: GHOST_CATALOG.md description: Ghost Catalog header specification for all repo artifacts project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [ghost-catalog, convention, spec] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# Ghost Catalog Header — Specification

Every artifact in this repo (`.md`, `.sql`, `.py`, `.ts`, `.tsx`, `.json`, `.bat`, `.sh`) MUST carry a Ghost Catalog header so it is self-describing and corpus-indexable.

## Formats
- **Markdown / SQL / SVG** (text files): HTML comment on the FIRST line.
  ```html
  <!-- file_id: SOM-DOC-0901-v1.0.0 name: GHOST_CATALOG.md description: ... project_id: ... category: doc tags: [...] created: YYYY-MM-DD modified: YYYY-MM-DD version: x.y.z agent_id: ... -->
  ```
- **TypeScript / TSX** (`//` comment). Do NOT use `<!-- -->` inside `.ts`/`.tsx` — esbuild breaks on HTML comments (cost a prior build failure).
  ```ts
  // file_id: SOM-TS-0001-v1.0.0 name: auth.ts description: ...
  ```
- **Python / Shell / Bat**: shebang-or-first-line `#` comment.
- **JSON** (package.json etc.): corpus builder may prepend `# ==== file_id ...` lines; strip before parse:
  ```bash
  grep -v '^#' f.json > f.json.tmp && mv f.json.tmp f.json
  ```

## Required fields
| field | meaning |
|---|---|
| `file_id` | `SOM-<TYPE>-<NNNN>-v<semver>` (DOC, TS, PY, SQL, SH, BAT) |
| `name` | filename |
| `description` | one-line purpose |
| `project_id` | `PREDICTION-MARKET-ANALYSIS` |
| `category` | doc / script / sql / lib / app / config |
| `tags` | `[...]` keywords |
| `created` / `modified` | `YYYY-MM-DD` |
| `version` | `x.y.z` |
| `agent_id` | `HERMES-AGENT` |

## Authority
This file is the authoritative reference for the Ghost Catalog convention (per SoMaCoSF `says-hub/skills/ghost-catalog`). Deviations require an explicit override note in the header.
