import time
import functools
import logging

logger = logging.getLogger(__name__)

def retry_on_exception(exceptions=(Exception,), max_retries=3, initial_delay=1.0, backoff_factor=2.0):
    """
    Retry decorator for external API calls.
    
    Args:
        exceptions: Tuple of exceptions that should trigger a retry.
        max_retries: Maximum number of retries before giving up.
        initial_delay: Initial delay in seconds before the first retry.
        backoff_factor: Multiplier for the delay after each retry.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"Failed after {max_retries} retries: {func.__name__}. Error: {e}")
                        raise
                    
                    logger.warning(f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {delay}s due to: {e}")
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator
