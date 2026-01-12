---
requires: [vertical_name, vertical_description, candidate_verticals_json, sample_entities_json, min_confidence]
---
New vertical name: {{ vertical_name }}
New vertical description: {{ vertical_description }}

Candidate canonical vertical names (JSON array):
{{ candidate_verticals_json }}

Sample extracted entities from the new vertical (JSON):
{{ sample_entities_json }}

Decide whether the new vertical should reuse one of the candidate canonical verticals.

Guidelines:
- Set match=true only if the candidate is clearly the same domain or a strict superset, and overlap should be high.
- match must be false for mismatched domains (e.g. motorcycles vs cars).
- confidence should be high only when certain. Use {{ min_confidence }} as the minimum threshold for match=true.
- If match=false, propose a stable canonical vertical name that groups the new vertical appropriately.

