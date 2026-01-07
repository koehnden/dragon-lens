I do not see what ww achieved with this implementation. I still see the LLM call blocks any other processing:
```
[2026-01-06 21:49:01,397: INFO/MainProcess] Task workers.tasks.run_vertical_analysis[3b2da598-7063-4123-97d4-b9dd092cc10e] succeeded in 145.08906179195037s: None
[2026-01-06 21:49:01,403: INFO/MainProcess] Task workers.tasks.run_vertical_analysis[d6913a27-c48d-4843-9e55-960b63a8a449] received
[2026-01-06 21:49:01,403: INFO/MainProcess] Starting vertical analysis: vertical=1, provider=deepseek, model=deepseek-chat, run=2
[2026-01-06 21:49:01,405: INFO/MainProcess] LLM parallel fetch: enabled=True, concurrency=3, prompts=1
[2026-01-06 21:49:02,298: INFO/MainProcess] HTTP Request: POST https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"
[2026-01-06 21:49:26,815: INFO/MainProcess] Processing prompt 2
```
As you can sse in the logs, we are still just waiting for the deepseek api to give an response!
Maybe we benefit more from running all remote LLM calls in the `POST /api/v1/tracking/jobs` first, e.g. all prompt for all models or all for a single model.
Wdyt? 


How about changing the processing order. For all prompts given in `POST /api/v1/tracking/jobs` we do:
1. Run all LLM call given is `POST /api/v1/tracking/jobs` for all models assync or using multi-threading or both and store results in memory (model, prompt, prompt_result)
2. Loop over results in 1. and translate all prompts and them. Bulk insert them in SqlLite
3. Process all prompt results, e.g. brand and product extraction
4. Start Consolidation steps
5. Bulk insert all extraction results in SqlLite
We could also do 2. and 3. into one step without bulk insert the prompts results and their translation. Note
sure which data structure could make sense to store result In-Memory. Maybe a simple Dictionary or we use Redis for store intermediate
result if it does not slow down the process much. 
Wdyt? Could this speed up a job from `POST /api/v1/tracking/jobs`. Is it doable? What are downsides of this approach?


Yes I want “process prompt A while prompt B is still waiting”! If we move to Postgresql for the dragonlens.db.
Would it be easier to speed up?

Ok let's move to Postgresql for storing data in dragonlens.db. I'm not sure if we need to keep SqlLite for 
`data/knowledge.db`. I would like to store `data/knowledge.db` in the git repo so the user can upload feedback on brand and product extraction.
Maybe there is a cleaner solution for this, but it's definitely not postgresql or at least without hosting it on the cloud.
Can you make a plan to migrate all the schema `dragonlens.db` to postgresql and how to replace SqlLite with postgresql in our prompt processing pipeline!
Keep in mind the Plan is:
Once on Postgres, the simplest way to get “process prompt A while prompt B is waiting” is usually Celery fan-out/fan-in:
      - group(process_prompt.s(...)) for each prompt (each task does: reuse-check → LLM call → persist answer → extraction → persist mentions)
      - then a chord(...)(consolidate_run.s(run_id)) callback to do steps 4–5 once all prompts finish
      - This naturally overlaps waiting prompts with processing prompts and avoids “async inside Celery” complexities.
  - You’ll still need rate limiting / semaphores (remote API limits, Ollama local resource limits), but those become straightforward (Celery queue routing, per-task
    throttling, or Redis-based rate limits).
Do not code yet! Plan the migration and all related things!


