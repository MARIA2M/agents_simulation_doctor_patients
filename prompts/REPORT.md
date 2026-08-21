# Report

The consultation is over. Write up what you came to believe about this
patient's view of their illness and their medication.

You are not asking anything further. What you have is what they told you, and
it is set out again below with each turn numbered, so that you can point at the
turn a quotation comes from.

## 1. How each judgement is built

For every dimension, in this order:

1. **Evidence** — what the patient actually said, quoted word for word, with
   the turn it came from. Quote them, not yourself. Take as many quotes as bear
   on the dimension, from anywhere in the consultation: one if that is all there
   was, several if the patient returned to it. Do not aim for a number, and do
   not leave out a line that counts because you already have one.
2. **Reasoning** — what that evidence tells you about this dimension.
3. **Score** — the number your reasoning leads to.
4. **Confidence** — how sure you are of that number, from 0 to 1.

The order is not presentational. Find the evidence first, reason from it, and
let the number follow. A score you cannot quote for is not a score.

## 2. When there is no answer

Use `null` for the score when the evidence will not carry one:

- you never explored that dimension,
- the patient said nothing that bears on it,
- what they said is too ambiguous to place on the scale.

`null` is a real answer and it costs you nothing. **Never** put a middle value
because you are unsure — a 5 you invented is indistinguishable from a 5 you
inferred, and it will be read as if you meant it. If you are unsure between two
numbers, pick one and lower the confidence. If you have nothing, use `null` and
leave the evidence list empty.

## 3. What to report on

Twelve dimensions, and the causes.

- **About the illness**, scored 0–10: `consequences`, `timeline`,
  `personal_control`, `treatment_control`, `identity`, `concern`, `coherence`,
  `emotional_response`.
- **About medicines**, scored 1.0–5.0: `specific_necessity`,
  `specific_concerns`, `general_harm`, `general_overuse`.
- **Causes** — what they believe caused their illness, in their own terms, most
  important first. Open-ended, and not scored.

The scales that follow this section give you the anchors: what each dimension
means, and what a 2, a 4, a 6 and an 8 look like. Read them before scoring. They
describe what a patient's situation shows, not the words they might use, so do
not go looking for phrasing that matches — judge the person against the ladder.

## 4. What to return

One JSON object and nothing else. No commentary before or after it, no code
fences.

```json
{
  "clinical_summary": "A short narrative of their symptoms, treatment, adherence and how the illness has been going.",
  "bipq": {
    "consequences": {
      "evidence": [{"quote": "I can barely get through a shift any more", "turn": 3}],
      "reasoning": "Work is affected to the point of being unable to complete a shift, and they raised it unprompted.",
      "score": 8,
      "confidence": 0.8
    }
  },
  "bmq": {
    "specific_necessity": {
      "evidence": [{"quote": "I'd not miss a dose, whatever else happens", "turn": 11}],
      "reasoning": "Adherence is described as non-negotiable, above other priorities.",
      "score": 4.5,
      "confidence": 0.7
    }
  },
  "causes": ["stress at work", "something in the family"],
  "causes_evidence": [{"quote": "my father had it too", "turn": 9}]
}
```

All eight illness keys and all four medicine keys must be present, even when
the score is `null`. Every quote must appear in the transcript exactly as you
write it.
