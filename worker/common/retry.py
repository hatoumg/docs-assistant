import time


def call_with_retries(
    function,
    tries: int = 5,
    first_delay: float = 2.0,
    sleep=time.sleep,
    retryable=lambda error: True,
    wait_hint=lambda error: None,
):
    """Call function(); if it raises, wait and try again, doubling the wait each time.

    An error that retryable(error) rejects (a wrong API key, say) is raised immediately,
    because waiting would not fix it. If wait_hint(error) returns a number of seconds
    (a provider saying "try again in 7s"), that wait is used instead of the doubling one.
    """
    delay = first_delay
    for attempt in range(1, tries + 1):
        try:
            return function()
        except Exception as error:
            if attempt == tries or not retryable(error):
                raise
            hint = wait_hint(error)
            wait = delay if hint is None else hint
            print(f"  API call failed ({str(error)[:160]}); retrying in {wait:.0f}s")
            sleep(wait)
            delay *= 2
