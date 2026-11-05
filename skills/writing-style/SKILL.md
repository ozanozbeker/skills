---
description: Plain-language prose a person reads. Use when writing or reviewing a docstring, a comment, a README or docs page, an error message, a commit message, a pull request body or an issue.
name: writing-style
---

# Writing style

Every sentence a person reads follows this page: a docstring, a comment, an error message, a config comment, a docs page, a commit message, an issue, a pull request body, a reply in chat.
A review applies every section below to every sentence.
A document an agent reads, such as a `CLAUDE.md`, an `AGENTS.md` or a skill, follows `writing-for-agents` instead when that skill is installed; without it, this page applies.

## Plain language

ISO 24495-1 sets the standard: the reader gets what they need, finds it fast, understands it on one pass, and can act on it.

- Write one idea per sentence.
  A sentence that needs two commas to join its clauses is two sentences.
- Use active voice and the present tense.
  Name the thing that acts, and name it first.
- Use common words: `because`, not `on the grounds that`.
- Write the plain clause, not the cleft: `Sharing it stops two checks disagreeing`, not `sharing it is what stops two checks from disagreeing`.
- Put the point first.
  The first sentence gives the answer, and the rest gives the reason.
- Keep the domain word.
  Simplify the grammar, not the vocabulary: `idempotent`, `serialize` and `schema` stay.

## Say what happens

Code raises, sets, reads, receives, returns and guarantees.
The code writes, passes, copies and keeps data.
A metaphor or a personification is a sentence that has not yet said what happens.

Give every sentence a verb, including a heading's description and a caption.
"The loader, and the check that rejects bad rows" becomes "`load` reads the file, and `validate` raises on a row that does not match the schema".

Use the word an upstream library or API already uses, in the meaning it has there.
If the upstream term is `job`, write `job`, not `task`.
Coin a term only for something the code names, such as a function, a class or a setting.
Define it in the repo's glossary beside the words it replaces, or in the docstring of the thing it names when the repo has no glossary.

## Asides

Use a colon, a semicolon, a comma, or a second sentence where an em dash would go.
An em dash brackets an aside that reads better as its own sentence.
This holds in code, comments, docstrings, commit messages, issues, pull request bodies and chat, and a `--` that stands in for one counts.

## Rationale, not usage

The reader is a future engineer who can reconstruct usage from the code and cannot reconstruct rationale: why this library over the alternative, why a name departs from convention, why a check runs at this layer.
Write what the reader cannot determine by looking at the thing in front of them: what was measured, what surprised you, and what the reader could not have known.
Before writing a justification, ask whether `git log`, the repo's own docs, or a config file already holds it; if so, skip it.

Usage is for the public surface, and the tidyverse reference pages are the model for it: one page per public object, every parameter and the return value described, and an example that runs on data the package ships.
The narrative, the why-and-when, goes in a guide page, as a tidyverse article does, and the reference page links to it.

## Short

Across a source tree, docstrings and comments stay under 40% of the characters.
Measure it when a rewrite is the point.
These limits keep it there:

- A private function's docstring is its summary line, plus a sentence only for a reason the name, the annotation and the body do not show.
- A module docstring is at most three sentences: what the module holds, how it relates to the modules beside it, and the one constraint a maintainer must know.
- A comment is one line, for a reason the code does not show, and is a sentence with a capital and a full stop.
  It records no history.
- A test's docstring says how, at the top: the goal and the method, so a reader can skip the body.
- A commit message is read where a pull request description never appears, in `git blame`.
  Write the message for that reader.
- A measurement or a declined design goes in an ADR or a research note, and the docstring links to it in one sentence.
- In a guide page, a sentence introduces every list, and a page has at most three callouts.
