In the UI I see that all brands name in the "Brands Overview" table are in Chinese.

<expected behaviour>
<English name> (<Chinese name if applicable>) e.g. BYD (比亚迪).
<expected behaviour>

<actual behaviour>
Current brand table look like this:
```
Brand,Mention Rate,Share of Voice,Top Spot Share,Sentiment Index,DVS
比亚迪,71.4%,18.6%,35.7%,0.6,0.303
吉利,64.3%,10.6%,14.3%,1,0.292
哈弗,57.1%,9.8%,14.3%,1,0.287
本田,50.0%,5.8%,0.0%,1,0.235
奇瑞,14.3%,3.2%,7.1%,1,0.234
广汽,7.1%,2.5%,7.1%,1,0.229
广汽传祺,7.1%,1.1%,0.0%,1,0.206
别克,7.1%,1.1%,0.0%,1,0.206
广汽丰田,7.1%,1.0%,0.0%,1,0.206
马自达,7.1%,1.0%,0.0%,1,0.206
荣威,7.1%,0.9%,0.0%,1,0.205
日产,7.1%,0.7%,0.0%,1,0.204
大众,50.0%,7.3%,7.1%,0.714,0.201
丰田,64.3%,10.1%,14.3%,0.556,0.2
长安,35.7%,6.2%,7.1%,0.6,0.172
理想,57.1%,7.8%,7.1%,0.5,0.161
特斯拉,42.9%,6.2%,7.1%,0.5,0.151
奥迪,21.4%,2.1%,0.0%,0.333,0.079
问界,35.7%,4.1%,0.0%,0.2,0.065
VW,0.0%,0.0%,0.0%,0,0
``` 
As you can see, except the primary brand set by the user "VW", all brands are in Chinese.
Can you check why this is the case and how brands are passed to the streamlit UI right now. 
Do not code yet! Make yourself familiar with the process now!

I do not think the wikidata helps us. It's too limited and does not have good Chinese data for most verticals.
Let's try to add or fix the translation of brands using Qwen. If only a Chinese name is present the brand/product should
be translated into English and we display <English name> (<Chinese name if applicable>) e.g. BYD (比亚迪). We need Qwen to 
be sure about the translated name and give it context about the vertical and the it should not do a literal translation!
If only an English name is extracted for the brand/product. We can stick to it and no translation to Chinese is needed.
We only show the English name in this case. 
Can you make a plan how to implement this and how to enhence the Qwen translation prompt for brand (if it exists) with suitable guardrails so it does not do any weird stuff.
Do not code yet. Plan with me!

1. Let's do brands and product together. I assume it could give qwen more context.
2. settings.ollama_model_translation, but I think they are both Qwen 7b if I'm not mistaken!

1. Yes, I think even 30 should do!
2. Let's retry these failed once one time again, otherwise use Chinese as a fallback

1. 大众 Volkswagen -> Volkswagen so just use the English name and skip the translation.
2. Only for those in the current run. 