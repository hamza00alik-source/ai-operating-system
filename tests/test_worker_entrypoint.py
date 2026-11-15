def test_standalone_worker_entrypoint_is_disabled_without_owner_provider_gate(monkeypatch):
    import worker_main

    monkeypatch.setattr(
        worker_main,
        "create_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not start")),
        raising=False,
    )
    assert worker_main.main() == 2
