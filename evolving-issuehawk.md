# Plan: Evolving IssueHawk (LFX / GSoC & Dynamic Growth Engine)

## Executive Summary
Upgrade IssueHawk from a static "good first issue" beginner scraper into an evolving, adaptive open-source career accelerator that tracks developer progression, curates high-impact contributions from premier foundations (CNCF, Linux Foundation/LFX, Apache, GSoC), and evaluates issues using a High-Impact Portfolio Rubric.

---

## Decisions & Architectural Strategy
1. **Hybrid Progression Engine**: Track developer skill tier (`apprentice` -> `contributor` -> `core_contributor` -> `mentorship_ready`), automatically syncing GitHub merged PRs while supporting CLI commands (`--progress`, `--complete <url>`, `--sync-profile`).
2. **Foundation Registry & High-Impact Search**: Remove hardcoded `label:"good first issue"`. Introduce a curated registry of top open-source foundations (CNCF, LFX, Apache, GSoC) and dynamic GitHub queries using tier-appropriate labels (`help wanted`, `enhancement`, `lfx-mentorship`, `gsoc`, `RFC`, `core`).
3. **High-Impact Portfolio Rubric**: Gemini 2.5 Flash prompt evaluates architectural depth (multi-file logic, API design, concurrency, performance), portfolio/CV value, and maintainer responsiveness, filtering out trivial single-line changes.
4. **Rich Terminal & Newsletter Polish**: Update CLI reports, Rich viewer, and HTML newsletter with progression status badges, foundation tags (`[CNCF]`, `[LFX]`, `[Apache]`), and portfolio impact scores.

---

## Actionable Task Breakdown

### Task 1: Foundation & Program Registry (`tools/registry.py`)
- Create curated registry of LFX, CNCF, Apache, and top GSoC repositories and organizations.
- Define queries, priority labels, and foundation metadata tags.
- **Verification**: Unit tests verifying registry structure and queries.

### Task 2: Profile & Progression Schema (`profile.yaml` & `tools/profile.py`)
- Extend `DeveloperProfile` schema: `github_username`, `tier` (`apprentice`, `contributor`, `core_contributor`, `mentorship_ready`), `target_foundations`, `xp`, `track`.
- Update `profile.yaml` with realistic intermediate-to-advanced settings targeting LFX/GSoC.
- **Verification**: `load_profile()` parses new fields with backward-compatible defaults.

### Task 3: Developer Evolution Engine (`tools/evolution.py` & `tools/memory.py`)
- Add database schema migrations in `memory.db` for user milestones, completed issues, and XP logs.
- Implement GitHub API sync to fetch user's merged PRs (`author:{username} type:pr is:merged`).
- Implement tier graduation logic and CLI milestone handlers (`mark_issue_completed`, `get_developer_stats`).
- **Verification**: Unit tests for XP calculation, tier upgrades, and database tracking.

### Task 4: Dynamic Search & Collector Refactor (`tools/github_api.py` & `tools/scraper.py`)
- Remove hardcoded `good first issue` query constraints.
- Dynamically build queries based on active `tier` and `target_foundations`.
- Add queries targeting foundation repositories and high-impact labels (`help wanted`, `lfx-mentorship`, `gsoc`, `enhancement`, `RFC`).
- **Verification**: Collector returns diverse candidate issues matching the developer's tier.

### Task 5: High-Impact Portfolio Rubric (`tools/llm.py`)
- Revise system prompt in `tools/profile.py` / `tools/llm.py` to assess architectural depth and CV/mentorship uplift.
- Update `IssueScore` schema with `impact_score` (1-10) and `portfolio_rationale`.
- **Verification**: Gemini prompt validation test with sample issues.

### Task 6: CLI & Reporter Integration (`main.py`, `tools/reporter.py`, `tools/viewer.py`)
- Add CLI flags: `--progress`, `--complete <url>`, `--sync-profile`.
- Update report generator, HTML newsletter, and Rich terminal viewer to display developer tier, foundation tags, and portfolio impact badges.
- **Verification**: `uv run python main.py --progress` and `uv run pytest` pass cleanly.

### Task 7: Full Test Suite & Validation
- Update existing tests (`test_profile.py`, `test_memory.py`, `test_triage.py`, `test_dispatchers.py`) and add `test_evolution.py`.
- Run `uv run pytest` and verify end-to-end functionality.
