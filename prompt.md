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

I want to be able to do the AI correction for the whole vertical. Can we remove "Select Run" dropdown and enable 
correction for the whole vertical if "LLM Model" is select as "All". 
Here is a plan to do this:

 Plan: Vertical-Level AI Corrections

 Goal

 Enable AI corrections for an entire vertical (all completed runs) when "LLM Model" is set to "All", instead of requiring a specific run to be selected.

 Current State

 - AI corrections work at the run level only (POST /runs/{run_id}/ai-corrections)
 - KnowledgeAIAuditRun.run_id is NOT NULL (single run)
 - Vertical export already exists: build_vertical_inspector_export(db, vertical_id)
 - The audit pipeline is generic and can process any list of export items

 Approach

 1. Database Schema Change

 Add new fields to KnowledgeAIAuditRun model to support vertical-level audits:

 File: src/models/knowledge_domain.py
 - Make run_id nullable (or add a sentinel value like 0 for vertical audits)
 - Add is_vertical_audit: Boolean flag to distinguish audit type

 2. New API Endpoint

 Create vertical-level AI correction endpoint:

 File: src/api/routers/ai_corrections.py
 - Add: POST /verticals/{vertical_id}/ai-corrections
 - Reuse existing AICorrectionCreateRequest schema
 - Return same AICorrectionRunResponse

 3. Execution Logic Update

 Modify execution to support both run and vertical modes:

 File: src/services/ai_corrections/execution.py
 - Check audit.is_vertical_audit flag
 - If true: use build_vertical_inspector_export(db, vertical_id)
 - If false: use existing build_run_inspector_export(db, run_id)
 - Rest of pipeline stays the same (batching, report, feedback)

 4. Persistence Layer Update

 File: src/services/ai_corrections/persistence.py
 - Modify create_audit_run() to accept optional run_id and is_vertical_audit flag
 - Update queries for latest_audit_run() to work with vertical audits

 5. UI Changes

 File: src/ui/pages/run_inspector.py
 - When "LLM Model" = "All": Hide run dropdown, show "Correct Vertical with AI" button
 - When specific model selected: Show run dropdown and existing "Correct with AI" button
 - Add new API call function _start_vertical_ai_correction(vertical_id, provider, model_name, dry_run)

 Files to Modify

 1. src/models/knowledge_domain.py - Add is_vertical_audit field
 2. src/api/routers/ai_corrections.py - Add vertical endpoint
 3. src/services/ai_corrections/execution.py - Add vertical execution path
 4. src/services/ai_corrections/persistence.py - Update create/query functions
 5. src/ui/pages/run_inspector.py - UI changes for vertical mode

 Design Decision

 - Scope: When "All" is selected, analyze ALL completed runs in the vertical regardless of model
 - No model filtering in vertical mode (simplifies implementation, gives most comprehensive data)

 Verification

 1. Restart API and Streamlit
 2. Go to Run Inspector, select a vertical
 3. Set "LLM Model" to "All"
 4. Click "Correct Vertical with AI"
 5. Verify metrics show aggregate precision/recall across all runs
 6. Verify review items show items from multiple runs (different run_ids)

Can you check if the plan make sense and update it if needed! Do not code yet! Discuss the plan with me!


We need to ensure that improvement are also used for similar verticals where same brands likely appear, e.g. "Car", "SUV", "Family Car", "Electric Vehicles" should all have the same corrections and improvements applied to them!
Update the plan accordingly!

Before we start, review what the ai correction from the `/api/v1/verticals/{vertical_id}/ai-corrections` endpoint actually does
and how it store in Turso to make sure we can use the correction as few shot and that they are in the format you expect!
Refine the plan after researching this! Do not code yet!



 the plan! Anything else we need to discuss before we start coding?
 
I do not get why you suggest Option A? Why would we ever exclude HIGH and VERY_HIGH, allow LOW/MEDIUM
Shouldn't it be the exact opposite, i.e. only include HIGH and VERY_HIGH and exclude LOW/MEDIUM or do I miss something here
Do not code yet! Answer the question!

Only use HIGH/VERY_HIGH with a priority of VERY HIGH. If less then 5 example exist just pass the example that exists.
If no example exists then pass nothing! Do not use MEDIUM!