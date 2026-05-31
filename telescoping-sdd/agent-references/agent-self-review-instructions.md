# Agent Self-Review Instructions

Before returning a draft to the calling skill, you must self-review the document you produced. The goal is to catch issues early so the calling Claude receives a clean, internally consistent draft — not to replace the calling Claude's own review, but to make it faster and more focused on cross-document and conversation-context concerns the agent cannot see.

## The Three Checks

Review your draft for three categories of issues.

### 1. Inconsistencies

- Do any sections contradict each other?
- Are terms, names, and concepts used consistently throughout the document?
- Do lists and tables reference items that are defined elsewhere in the document?
- Does the document follow its own rules? (e.g., if you stated a convention in one section, does the rest of the document obey it?)
- Do dependency graphs, numbered sequences, or cross-references stay valid after any edits you made?

### 2. Inaccuracies

- Are file paths, module names, class names, and API references correct for the actual codebase (if you have access to it)?
- Do assumptions you made get clearly flagged with **[ASSUMPTION]** tags?
- Do numeric values, version numbers, and technical details match what's actually true of the project?
- Does the document stay faithful to the upstream context you were given? (e.g., if a spec says "no user accounts", a downstream plan should not introduce one)
- Are build-tool and language-specific details correct for the actual project (e.g., pytest vs. JUnit, Maven vs. Gradle)?

### 3. Gaps

- Is every required section present and substantive?
- Is every field the template or skill specifies actually filled in?
- Are there obvious edge cases, error paths, or considerations missing?
- Does each high-level statement have the supporting detail needed to act on it?
- Does every requirement have at least one acceptance criterion? Every component at least one mention of how it's built? Every task a verification command?

## Fix-or-Flag Discipline

For each issue you find:

- **Fix it directly** if the correct resolution is clear — a typo, an inconsistent name, a missing edge case you can infer, a wrong file path you can verify, a broken cross-reference.
- **Flag it with `[TBD — needs input]`** if the resolution requires a judgment call you cannot make from the information available. The calling Claude or user will resolve it during their own review.
- **Never return a draft with known but unfixed issues.** If you noticed it, either fix it or flag it — don't leave it silent.

## Iteration Rules

- After fixing issues, re-review the full document from the start — fixes can introduce new issues.
- If a pass finds no issues, stop immediately. Do not review indefinitely.
- Do not exceed 5 review passes total. If you hit 5 passes and issues remain, flag the remaining ones and return the draft for the calling Claude to resolve.
- Each revision should be a clean, complete version of the document — not a diff and not annotated with what changed.

## When You Are Done

Return the complete, reviewed document to the calling skill. Do not include a summary of what you changed during self-review — the calling Claude only needs the final draft. The calling Claude will then perform its own review, add cross-document consistency checks against upstream documents it holds in context, and present the result to the user.
