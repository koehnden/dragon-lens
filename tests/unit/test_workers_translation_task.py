from workers import tasks


def test_translate_text_task_uses_translater_service(monkeypatch):
    captured: dict[str, str] = {}

    class StubTranslaterService:
        def translate_text_sync(
            self,
            text: str,
            source_lang: str,
            target_lang: str,
        ) -> str:
            captured["text"] = text
            captured["source_lang"] = source_lang
            captured["target_lang"] = target_lang
            return "translated-text"

    monkeypatch.setattr(tasks, "TranslaterService", StubTranslaterService)

    result = tasks.translate_text.run("Hello", "English", "Chinese")

    assert result == "translated-text"
    assert captured == {
        "text": "Hello",
        "source_lang": "English",
        "target_lang": "Chinese",
    }
