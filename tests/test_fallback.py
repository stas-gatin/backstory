from backstory import config, meta


class Answer:
    def __init__(self, code, body):
        self.status_code, self._body, self.text, self.headers = code, body, str(body), {}

    def json(self):
        return self._body


def test_spark_falls_back_when_the_api_says_model_not_found(monkeypatch):
    sent = []

    def post(url, headers, data, timeout):
        model = __import__("json").loads(data)["model"]
        sent.append(model)
        if model == config.SPARK:
            return Answer(404, {"error": {"code": "model_not_found"}})
        return Answer(200, {"model": model, "output_text": "ok"})

    monkeypatch.setattr(meta.requests, "post", post)
    monkeypatch.setattr(meta.time, "sleep", lambda s: None)
    j = meta._post({"model": config.SPARK, "input": "hi"})
    assert sent == [config.SPARK, config.FALLBACK[config.SPARK]]
    assert j["model"] == config.FALLBACK[config.SPARK]


def test_a_call_with_web_search_is_asked_again_without_it(monkeypatch):
    sent = []

    def post(url, headers, data, timeout):
        body = __import__("json").loads(data)
        sent.append((body["model"], bool(body.get("tools"))))
        if body.get("tools"):
            return Answer(404, {"error": {"code": "model_not_found"}})
        return Answer(200, {"model": body["model"], "output_text": "ok"})

    monkeypatch.setattr(meta.requests, "post", post)
    monkeypatch.setattr(meta.time, "sleep", lambda s: None)
    meta._post({"model": config.SPARK, "input": "hi", "tools": [{"type": "web_search"}], "include": ["x"]})
    assert sent == [(config.SPARK, True), (config.FALLBACK[config.SPARK], True), (config.FALLBACK[config.SPARK], False)]
