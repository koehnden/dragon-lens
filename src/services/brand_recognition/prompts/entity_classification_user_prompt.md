---
id: entity_classification_user_prompt
version: v1
description: User prompt for classifying a single entity
requires:
  - text
  - entity
---
Text: {{ text }}

Entity to classify: {{ entity }}

Classify this entity. Output JSON only:
