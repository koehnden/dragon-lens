I would like to create another process that uses the JSON we create in the Runs Inspector Buttons that 
uses a more capable LLM like deepSeek-reasoner to:
- Calculate precision and recall of our brand extraction
- Clusters the error by category and give examples -> e.g. "Brand Duplicates", "Missed Brand", "Irrelevant for Vertical" etc
- Automatically reports mistakes, corrects them and gives a reason why this is a mistake and stores them into Turso DB. Similar to our mechanism in the "Feedback" page in the UI
Can we explore if this is possible and how to implement this?
Do not code yet! Explore the code and discuss a plan with me!


About the choices:
1. Suggestion should be applied without human interaction for error where deepseek is very confident. For errors where deepseek is unsure we probably need a human check. We probably need the not sure items to appear on the "Run Inspector" UI page after we trigger the deepseek correct. 
2. We need brands+products+mappings. 
3. Turso because it should be used as if a human gave feedback. It should help the cheaper system to learn from mistakes. We probably need a flag in the DB that is called reviewer="user|deepseek-reasoner"
4. batch-5 prompts!
We need a button in the Run Inspector UI called "correct with AI". After the correction is finished. The UI should show the precision and recall, clusters of common mistakes with 1-2 examples and the item where deepseek is not confident. On the items where deepseek is not confident we should have an apply button that submits this feedback to the system and stores it in Turso.
Update the plan! Do not code yet!

On the API, make sure that the llm model we use for `ai-correct` is a parameter and we can use all models that are available in `src/services/remote_llms.py`. deepseek-reasoner should be the default model for now.
Update the plan! Do not code yet!

If openrouter key is available we can use it as a backup!

Auto-apply should be there for all actions. Threshold for replace/add/validate actions should be higher than for reject. We probably need to experiment thresholds. How do you plan the create the thresholds? 