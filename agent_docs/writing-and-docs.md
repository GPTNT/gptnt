# Writing and documentation

Use this guide when changing an identifier, comment, docstring, error message, README, or page under
`docs/`, and when simplifying code for readability.

## Prose, docstrings, and comments

<!-- rule:gptnt:201 -->

- Describe current behaviour without requiring the reader to know the change that introduced it.
  Historical language is appropriate when current state, compatibility, or a migration depends on
  an earlier event. Version control is sufficient for implementation history that has no effect on
  current behaviour. Do not ban individual words without considering what the sentence means.

<!-- rule:gptnt:202 -->

- Use direct, literal prose and describe the mechanism instead of evaluating it. Remove
  introductions that delay the fact, marketing language, apologies, adjectives that only praise
  the implementation, and verbs that do not identify an operation. Capitalise a word to mark a
  condition a reader will otherwise get wrong, as `exception_recovery.py` does with `BUT` and
  `NOT`. Emphasis that carries no warning is padding. First-person plural is established in this
  project and does not need removing.
  Keep technical qualifications when they change the stated behaviour. Replace "this cleanly
  enables retries" with the state change or call that permits a retry. Phrases such as "single
  source of truth" and "raise or report the concrete exception" do not identify where a value is
  stored or which exception is raised. Replace vague constructions such as "call a player against a
  dataset" with the actual
  operations: load the player configuration, send dataset instances to the model, and score the
  responses.

<!-- rule:gptnt:203 -->

- Use literal descriptions instead of metaphors or coined shorthand. Define a domain term before
  using it. Replace a nickname when the code already has a more accurate identifier. Do not use
  `fix` to mean define, select, store, or make immutable. Name the actual operation. Reserve `fix`
  for correcting a defect.

<!-- rule:gptnt:204 -->

- Useful documentation identifies an input source, unit, calculation, state transition, invariant,
  or edge case that is not available from the adjacent name, signature, type, or code. A field named
  `display_name` does not need a sentence saying that it is a displayed name. Do not copy the
  surrounding file's documentation density when doing so would omit information that a caller or
  maintainer needs to understand the behaviour or preserve an invariant.

<!-- rule:gptnt:205 -->

- Match the length of a docstring to the behaviour it explains. A simple builder may need no
  docstring. A stateful calculation may need several sentences to identify the measurement, update,
  invariant, and edge-case input. Do not impose a line limit on necessary information.

<!-- rule:gptnt:206 -->

- Explain a conditional, edge case, ordering constraint, or state-dependent branch when its purpose
  is not apparent from the code. Put the explanation beside the narrowest code element to which it
  applies.

<!-- rule:gptnt:207 -->

- Use the same term when two passages refer to the same concept. Different abstraction levels may
  use different terms when the distinction is defined. For example, a calculation determines an
  omitted-entry count, and rendering uses that count to truncate model history.

<!-- rule:gptnt:208 -->

- Use separate sentences for separate facts. Prefer ordinary punctuation. Use an em dash only for a
  parenthetical statement that would also work in parentheses. Do not combine a requirement,
  rationale, and example into one sentence.

<!-- rule:gptnt:209 -->

- A workaround must identify the external constraint, the expected behaviour, and why the direct
  implementation fails under that constraint. This information distinguishes the workaround from
  accidental complexity.

<!-- rule:gptnt:210 -->

- Update documentation when a change alters the behaviour it describes. Add or expand user-facing
  documentation in the guide where users encounter a new CLI, configuration, or other exposed
  behaviour. Keep the implementation and its affected documentation in the same change. Do not
  change unrelated documentation as part of the task.

## Explaining non-obvious behaviour

<!-- rule:gptnt:211 -->

- Name each important value, operation, boundary, condition, and state change. State where a value
  comes from and which operation uses or changes it. Keep identifiers and prose consistent, and
  rename an identifier that forces the explanation to use an undefined metaphor or misstate the
  value. Prefer `measured_tokens` to `anchor` and `omitted_count` to `frontier` when those are the
  values stored by the code. Repeat the noun when `it`, `this`, `the count`, or `the size` could
  refer to more than one value.

<!-- rule:gptnt:212 -->

- Explain stateful logic in execution order: input and source, calculation, state change, invariant,
  then relevant edge case. Give each step its own sentence when combining the steps would obscure
  their relationship.

  For token truncation, identify which request the provider measured, how the available budget is
  calculated, which entries the calculation may omit, which entries remain, and how a zero
  measurement affects the stored omission count.

<!-- rule:gptnt:213 -->

- A test docstring may explain an invariant, calculation, fixture arrangement, or relationship that
  is not apparent from the test name and assertions. Use as many sentences as that explanation
  requires. Remove issue labels, editorial claims, and comments that merely translate an assertion
  into English.

Example:

> The remaining 20% covers response text added after the previous request and errors in the size
> estimates used to remove old turns. Tokens for the next observation are reserved separately.

The example identifies the unmeasured input and distinguishes it from the separately calculated
observation reservation.

## Code clarity

<!-- rule:gptnt:214 -->

- Use `mapping[key]` when the key must exist. Let a missing required key raise `KeyError`. Use
  `mapping.get(key)` when absence is an accepted state, then handle `None` explicitly.

<!-- rule:gptnt:215 -->

- Use a defaulting or filtering expression only when it preserves the intended treatment of falsy
  values. Use an explicit condition when `0`, an empty string, or an empty collection has a meaning
  distinct from absence.

<!-- rule:gptnt:216 -->

- Bind an intermediate variable when its name explains the value, avoids repeating a calculation, or
  makes a multi-step operation easier to inspect. Pass a single-use expression directly when the
  variable would not add information. `RET504` is disabled, so choose based on readability.

<!-- rule:gptnt:217 -->

- Omit a call argument that matches the declared default unless showing the value is necessary to
  explain the call or protect an intentional choice from a likely default change.

## Documentation mechanics

<!-- rule:gptnt:218 -->

- Put an explanation beside the narrowest code element it describes. Keep a module docstring to the
  module's purpose. Use a class docstring for relationships among fields or class-wide behaviour, a
  field explanation for information specific to that field, and a function docstring for the
  function's contract or reference URL. Use an inline comment for one statement, branch, or ordering
  constraint. Do not add a field explanation that only restates its name or type. For a model field,
  follow [`gptnt:420`](data-and-types.md#field-documentation-and-schema-metadata) to choose a string
  literal or schema metadata.

<!-- rule:gptnt:219 -->

- Maintain one canonical explanation for each topic. Link to that explanation from other pages
  instead of copying it.

<!-- rule:gptnt:220 -->

- Do not cite `CLAUDE.md`, `AGENTS.md`, or `agent_docs/` from released code. These files are
  repository working instructions, not product documentation.

<!-- rule:gptnt:221 -->

- Refer to code by function, class, field, or module name. Do not use a source line number that will
  become incorrect when the file changes.

<!-- rule:gptnt:222 -->

- Document a parameter default or fallback order when it is not apparent from the signature or when
  several parameters interact to determine it.

<!-- rule:gptnt:223 -->

- Link to official provider or project documentation for model lists, feature matrices, and setup
  steps maintained outside this repository. Keep the local explanation to the behaviour specific to
  `gptnt`.

<!-- rule:gptnt:224 -->

- Register every new documentation page in `zensical.toml` so it appears in site navigation.

<!-- rule:gptnt:225 -->

- On a concept or explanation page, connect components by stating why a boundary exists or how one
  decision affects the next part of the system. A sequence of definitions belongs in reference
  documentation; definitions on a concept page should support an explanation of the relationships
  between them.

<!-- rule:gptnt:226 -->

- Omit the module docstring. The documentation on the module's functions and classes already states
  what the module holds, and a module docstring repeats it. Add one only when the module has a
  constraint that no function or class states, such as an ordering requirement among its contents or
  an external format the whole module implements.

<!-- rule:gptnt:227 -->

- Begin a function or method docstring with an imperative verb. Write "Return the frozen entry"
  rather than "The frozen entry". A property may use a noun phrase because it names a value rather
  than an operation. `SuiteLock.entry_for` and `SuiteLock.select_entry` currently use both forms.

<!-- rule:gptnt:228 -->

- Make the smallest edit that fixes the problem when revising prose that already exists. Reorder
  words, drop a word, or split a sentence rather than rewriting the passage. Someone comparing the
  two versions should see the author tightening their own sentence. Keep every line within the
  configured line length: rewrapping a docstring is part of the edit, and the formatter does not
  reflow prose.

<!-- rule:gptnt:229 -->

- Keep the informal register already present in this project's prose. `Ofc`, `LOADS`, and "Bit of a
  hack but it works" carry the author's meaning and are not padding. `gptnt:202` covers the
  emphasis and first-person conventions that go with it.

<!-- rule:gptnt:230 -->

- Treat a string literal sent to a model as behaviour, not documentation. Do not edit it for style.
  `"Reply with the single word: READY."` in `src/gptnt/cli/checks/validation.py` reads as padded
  prose and must stay exactly as written.

## Review checklist

For every changed identifier, comment, docstring, error, test description, and documentation
paragraph, check:

1. Does the text identify the concrete value or operation?
2. Does a non-obvious explanation follow execution order?
3. Does each sentence add information that adjacent code does not provide?
4. Are the relevant invariant and edge cases included?
5. Does terminology match the distinctions in the implementation?
6. Can the text be understood without the diff that introduced it?
