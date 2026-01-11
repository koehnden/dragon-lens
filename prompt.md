I have a merge conflict in `src/ui/pages/results.py` when merging main branch into comparison-prompts branch.
The comparison-prompt branch implement a new feature that add brand and product comparison prompts to enhence the sentiment analysis.
The user can optionally input competitor brands he wants to compare the primary brand with and input comparison prompts.
All this is optional and if the user does input less than 20 prompt the system generates 20 - # prompt user input. 
The conflict result page needs to solve by putting the new sentiment part into a separate tab in needed like "Competitive Landscape", "Performance Analysis" etc.
Can you check how to resolve the conflict without changing the main branch behaviour and with adding the new feature?

We should reuse the vertical mappings also when using the user feedback, e.g. brands for vertical "Car" are relevant for vertical "SUVs" but not for "Motorcycles".
We need a mechanism to check for existing verticals in the Turso DB and reuse the feedback if a relevant vertical already exists.
If the user run "SUV" vertical runs, feedback from vertical "Cars" should be used. Thus we need to introduce an automatic vertical matching.
I suggest using Qwen yet again for this. We need to be conservative. So Qwen should be sure that the feedback from the existing vertical is relevant for the new vertical and brands likely overlap a lot.
Can you make a plan for this! Do not code yet!
