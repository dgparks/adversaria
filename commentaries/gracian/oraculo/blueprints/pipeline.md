Yes — gather secondary sources first, but the highest-leverage move is *not* "build a corpus and dump it as context." It's **build a per-maxim research dossier and design a multi-pass generation pipeline that defends against the two specific failure modes** AI hits when it tries to write philosophical commentary.

## The two failure modes you're designing against

1. **Shallow modernization.** The model strips Gracián to a LinkedIn aphorism ("network with intention!"). The historical specificity, the agonistic court-political register, the Jesuit-baroque texture all evaporate. The maxim becomes interchangeable with any other self-help text.
2. **Hallucinated scholarship.** The model produces sober, citation-styled prose that sounds erudite but invents Gracián scholars, misattributes Senecan/Tacitean influences, and confidently asserts contested interpretations. The veneer of philology is more dangerous than its absence.

Every architectural choice below is in service of these two.

## Phase 1 — Build a per-maxim dossier (this is most of the value)

Don't pile sources into a single context window. For each of the 300 maxims, build a `research/NNN.md` (or a `## Research` section inside `maxims/NNN.md`) containing:

- The original Spanish *and* the Maurer English, side by side.
- **One or two alternative English translations** when available (Joseph Jacobs 1892, L.B. Walton 1953). Triangulation is cheap insurance against Maurer's particular interpretive choices.
- The **Cátedra footnotes** for that maxim. Emilio Blanco's edition (which you already own as `spanish-blanco-catedra.html`) has dense per-aphorism scholarly notes — these are the single most valuable per-maxim resource. Extract them into the dossier; they're the philological backbone.
- A **glossary of key 17th-century terms** as they appear in this maxim — `prudencia`, `desengaño`, `dictamen`, `cordura`, `ingenio`, `agudeza`, `sutileza`, `recato`, `discreción`, `persona`. These don't map cleanly to their modern English cognates and the AI will mistranslate them by default.
- **Cross-references** to other Gracián works (*El Héroe*, *El Discreto*, *El Político*, *Agudeza y arte de ingenio*, *El Criticón*) where the same idea recurs. The Cátedra apparatus does much of this for you.
- 2–4 short excerpts (≤200 words each, with full citations) from secondary literature relevant to *that specific maxim* or its core concept.

The dossier is the AI's primary context. Generic "Gracián studies" content as a single dump produces synthesis-of-mush; a dossier scoped to one maxim produces sharp, defensible commentary.

## Phase 2 — Acquire a focused secondary corpus

You don't need a research library; you need the right ~15–25 sources. In rough priority order:

**Spanish-language philology / philosophy**
- Emilio Blanco's Cátedra edition (you have it) — the apparatus is the ground truth for textual issues.
- **Aurora Egido**, *Las caras de la prudencia y Baltasar Gracián* (Castalia, 2000) and *La rosa del silencio* (Alianza, 1996). Egido is the modern dean of Gracián studies; her readings are the closest thing to a consensus.
- Sebastián Neumeister, *Mito clásico y ostentación* (1992) — political-aesthetic context.
- Benito Pelegrín's introductions to his French translations of *El Héroe* / *El Político* (deeply philological).

**English-language scholarship**
- **Christopher Maurer's translator introduction** to *The Art of Worldly Wisdom* (you should have it in the PDF you extracted; if not, scan it in). It's the single best English-language entry point.
- **Jeremy Robbins**, *Arts of Perception: The Epistemological Mentality of the Spanish Baroque* (Routledge, 2007) — the indispensable book for situating Gracián within the *desengaño* / dissimulation tradition.
- John Beverley's essays on the Spanish baroque.
- Hans Speier, "The Social Conditions of the Ideal of Cultivation" — old but sharp on Gracián's social setting.
- Pierre Force, *Self-Interest before Adam Smith* (Cambridge, 2003) — has a crucial chapter on Gracián's reception by La Rochefoucauld and the moralistes; gives you the Anglo-French reception arc.

**Practical-philosophy framing (for the bridge to modern application)**
- Pierre Hadot, *Philosophy as a Way of Life* and *What is Ancient Philosophy?* — gives you the conceptual vocabulary for "philosophy as practice" without reducing to self-help.
- Bernard Williams, *Ethics and the Limits of Philosophy* (esp. on practical wisdom and the limits of moral theory).
- Cautiously: contemporary Stoicism literature (Pigliucci, Irvine). Useful as a *contrast set* — Gracián is decidedly not a Stoic and the differences are clarifying. Do **not** let it become the model's interpretive default.

**To explicitly avoid in the corpus:** generic "wisdom of Gracián" popularizations, business-self-help books that quote Gracián, and Robert Greene's *48 Laws of Power*. These are exactly the register you're trying to write *better than*; including them poisons the model's prior.

## Phase 3 — Audience profiles as first-class data

Treat each audience as a structured file (e.g. `audiences/engineering.yaml`, `audiences/sales.yaml`, `audiences/eng-manager.yaml`, `audiences/founder.yaml`). Each profile defines:

- **Role and seniority band.**
- **Concrete situations**: code review under political pressure, performance-cycle calibration, on-call escalation, sales-cycle disengagement, a skip-level meeting, OKR negotiation, a demo to a hostile customer, a layoff round.
- **Vocabulary they trust** (mentor, teammate, peer, postmortem, design doc).
- **Vocabulary banned** ("synergy," "leverage" as verb, "circle back," "rockstar," "ninja," "thought leader," "hustle," "grindset," "winning," "10x").
- **Tone**: skeptical, time-pressed, allergic to motivational rhetoric.
- **Length budget**: e.g. 300–450 words per audience commentary.

These files are the smallest source of the most generation-quality lift. Iterate them as you read your own drafts.

## Phase 4 — Multi-pass generation, never single-shot

A single "write a commentary" prompt is the worst possible architecture. Use a 4–5 stage pipeline. Each stage is a separate API call with a tightly scoped task and structured output.

1. **Philological pass** — *Inputs:* dossier. *Output:* 2–3 paragraphs answering "What is Gracián actually saying in this maxim, in his own historical register?" Required to quote at least one Spanish phrase. Forbidden to mention modern application. Forbidden to cite anything not in the dossier (this is the hallucination defense).
2. **Tension pass** — *Output:* 1 paragraph identifying the *difficulty* in the maxim — what Gracián concedes, what he leaves unresolved, where modern intuitions resist him. Without this, every commentary collapses into agreement.
3. **Bridge pass** — *Output:* a structured list of 4–6 contemporary tech-workplace *situations* where the principle applies — names of situations only, no prose, no advice.
4. **Application pass (per audience)** — *Inputs:* outputs of (1)–(3) + the audience profile. *Output:* the actual commentary draft for that audience. Hard constraints: must reference Gracián's actual phrasing at least once, must include the tension from (2), must avoid the banned vocabulary list, must not exceed length budget.
5. **Critique pass** — A separate model call that grades the draft against an explicit rubric: philological fidelity, presence of tension, absence of banned phrases, length, anti-LinkedIn-ness. Returns either `pass` or a numbered list of revisions.
6. **Revision pass** — If (5) returned revisions, run one more pass applying them.

This pipeline trades tokens for quality. Each pass is small and well-scoped, which both reduces hallucination and makes the failure mode of any single stage easier to debug.

## Phase 5 — Storage and human-in-the-loop

Extend `maxims/NNN.md` with role-tagged sections so everything stays in the one-file-per-maxim model you wanted:

```markdown
## Commentary — Engineering

status: ai-draft   <!-- ai-draft | revising | human-final -->
generated: 2026-04-17
model: claude-...
…draft prose…

## Commentary — Sales

status: human-final
…your prose…
```

Frontmatter grows accordingly:

```yaml
audiences:
  engineering: { status: ai-draft, generated: 2026-04-17 }
  sales:       { status: human-final }
```

`check_maxims.py` learns to enforce: every audience listed in frontmatter has a corresponding `## Commentary — <Audience>` section; never let an `ai-draft` get marked `published`; warn when a `## Research` section was updated after the latest `ai-draft` (because the dossier changed and the draft is now stale).

This keeps the AI output and your editorial work cleanly separated *within* the same file.

## Phase 6 — Validation that's real, not theatrical

Three checks worth automating:

- **Citation grounding**: every quoted Spanish phrase in any commentary must literally appear in the maxim's `## Spanish` section. Trivial regex check, catches paraphrase-as-citation hallucinations cold.
- **Banned-vocabulary lint**: per-audience banned-word list applied to the corresponding commentary section.
- **Length budgets**: enforced per audience.

These three alone will save you most of the editorial pain.

## Suggested phased rollout

**Week 1.** Acquire Maurer's intro, Robbins's *Arts of Perception*, Egido's *Las caras de la prudencia*, and a clean copy of the Cátedra footnotes. Write `scripts/build_dossier.py` that pulls the Cátedra footnotes per maxim into a `## Research` section inside `maxims/NNN.md` (or into a sibling `research/NNN.md`). Validate with check_maxims.

**Weeks 2–3.** Pick 5 maxims that are conceptually distinct (e.g. 1 *persona*, 7 *outshining the boss*, 13 *real or apparent intentions*, 47 *avoid commitments*, 76 *don't always be joking*). Hand-author dossier excerpts from the secondary sources for each. Hand-write a commentary in your own voice for each, *for one audience*. These are your gold-standard exemplars; every prompt later will reference them as few-shot examples.

**Weeks 4–6.** Implement the multi-pass pipeline (`scripts/generate_commentary.py`) on those 5 maxims. Iterate on prompts until the AI output is recognizably in-genre with your hand-authored ones — the gap will be visible and fixable. Add the citation-grounding and banned-vocab linters.

**Months 2–3.** Define audience profiles (start with two: Engineering and Sales). Generate drafts in batches of 25 maxims. Hand-edit aggressively. Track which prompt patterns produce the least editing burden — that's your prompt iteration signal.

**Later.** Add audiences as needed. Consider a small RAG layer over the secondary corpus only once you've outgrown the per-maxim dossier model — which you may never, because Gracián's maxims are short and self-contained enough that hand-curated dossiers genuinely outperform retrieval.

## A few non-obvious risks to flag

- Gracián is **not a Stoic** and AIs default to Stoic readings because Stoicism dominates the modern practical-philosophy corpus. Your prompts should explicitly instruct: do not assimilate to Stoicism without explicit textual warrant; note differences when relevant.
- Gracián is **a Jesuit priest writing in the Counter-Reformation court**. The agonistic, dissimulating, surveillance-aware quality of the maxims is constitutive, not incidental. AI tends to sand this off into "professional polish." Resist.
- Gracián's real native genre is **the *desengaño* tradition** — disillusionment as a starting epistemic posture. The bridge to tech-employee life is actually unusually clean here (every senior IC has the same baroque-court epistemics). Lean into this; it's your differentiator vs. generic wisdom-blogging.
- Maurer's translation is excellent but interpretive. For maxims where Maurer makes a strong choice (e.g. modernizing *persona* as "true person"), your dossier should record both the literal Spanish and Maurer's gloss, and your commentary should be aware of the translator's hand.

## TL;DR

Yes — gather secondary sources first, but the asset you're building is **a per-maxim research dossier**, not a "context corpus." Pair it with explicit audience profile files and a 4–5 stage generation pipeline (philology → tension → bridge → application → critique). Single-shot prompting on this material will fail; structured multi-pass prompting on dossier-grounded inputs is achievable and produces commentary you'll be willing to publish under your name.

Start with five hand-authored exemplars to anchor the pipeline; treat the AI drafts as a first revision, not a final draft, and store them under explicit `ai-draft` status in the same `maxims/NNN.md` files you already have.
