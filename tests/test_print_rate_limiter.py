import asyncio

from zebra_day.web.middleware import PrintRateLimiter, print_rate_limiter


def _run(coro):
    return asyncio.run(coro)


def test_default_print_rate_limiter_allows_three_labels_per_second() -> None:
    assert print_rate_limiter.max_requests == 3
    assert print_rate_limiter.window_seconds == 1.0


def test_print_rate_limiter_rejects_fourth_label_in_one_second() -> None:
    async def scenario() -> None:
        limiter = PrintRateLimiter(max_requests=3, window_seconds=1.0, max_concurrent=3)
        client_ip = "192.0.2.10"

        for _ in range(3):
            allowed, reason = await limiter.acquire(client_ip)
            assert allowed is True
            assert reason == ""
            limiter.release()

        allowed, reason = await limiter.acquire(client_ip)
        assert allowed is False
        assert "3 requests per 1.0s" in reason

    _run(scenario())


def test_print_rate_limiter_allows_next_second_window() -> None:
    async def scenario() -> None:
        limiter = PrintRateLimiter(max_requests=3, window_seconds=0.01, max_concurrent=3)
        client_ip = "192.0.2.20"

        for _ in range(3):
            allowed, _reason = await limiter.acquire(client_ip)
            assert allowed is True
            limiter.release()

        allowed, _reason = await limiter.acquire(client_ip)
        assert allowed is False

        await asyncio.sleep(0.02)
        allowed, reason = await limiter.acquire(client_ip)
        assert allowed is True
        assert reason == ""
        limiter.release()

    _run(scenario())
