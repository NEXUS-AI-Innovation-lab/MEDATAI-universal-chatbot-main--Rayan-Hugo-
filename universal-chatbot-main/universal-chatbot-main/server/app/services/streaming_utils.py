"""
Streaming Utilities for Async/Sync Bridge
==========================================

This module provides utilities for bridging synchronous generators with
async FastAPI endpoints, enabling real-time streaming of responses.

Architecture
------------
The challenge: Our LLM/RAG generators are synchronous (they use blocking I/O),
but FastAPI endpoints need to yield data asynchronously for proper streaming.

Solution: Thread-Queue Architecture

    ┌─────────────────┐         ┌─────────────────┐
    │  Background     │         │   Async Event   │
    │  Thread         │ ──────► │   Loop          │
    │                 │  Queue  │                 │
    │  - Runs sync    │         │  - Non-blocking │
    │    generator    │         │    queue reads  │
    │  - Puts items   │         │  - Yields items │
    │    to queue     │         │    to FastAPI   │
    └─────────────────┘         └─────────────────┘

Message Protocol:
    ('item', data)  - A yielded item from the generator
    ('error', exc)  - An exception occurred
    ('done', None)  - Generator completed

Timeout Values:
    - Queue poll: 0.1s (100ms) - balances responsiveness vs CPU
    - Event loop sleep: 0.01s (10ms) - allows other async tasks
    - Heartbeat: configurable (default 10s) - keeps connection alive

Usage:
    async for item in async_stream_wrapper(loop, my_generator, arg1, arg2):
        yield process(item)
"""

import asyncio
import queue
import threading
import time
from typing import Any, Callable, Generator, AsyncGenerator


async def async_stream_wrapper(
    loop: asyncio.AbstractEventLoop,
    generator_func: Callable[..., Generator],
    *args: Any,
    **kwargs: Any
) -> AsyncGenerator[Any, None]:
    """
    Wrap a synchronous generator for async iteration.

    Runs the generator in a background thread and yields items as they
    become available, allowing the async event loop to remain responsive.

    Args:
        loop: The asyncio event loop (use asyncio.get_event_loop())
        generator_func: A function that returns a generator
        *args: Positional arguments to pass to generator_func
        **kwargs: Keyword arguments to pass to generator_func

    Yields:
        Items from the generator

    Raises:
        Any exception raised by the generator
    """
    result_queue: queue.Queue = queue.Queue()

    def run_generator():
        """Background thread: runs generator and puts items to queue."""
        try:
            for item in generator_func(*args, **kwargs):
                result_queue.put(('item', item))
        except Exception as e:
            result_queue.put(('error', e))
        finally:
            result_queue.put(('done', None))

    # Start generator in background thread
    thread = threading.Thread(target=run_generator, daemon=True)
    thread.start()

    # Yield items as they come
    while True:
        # Non-blocking check with timeout
        # Timeout of 0.1s balances responsiveness vs CPU usage
        def get_with_timeout():
            try:
                return result_queue.get(timeout=0.1)  # 100ms polling interval
            except queue.Empty:
                return None

        result = await loop.run_in_executor(None, get_with_timeout)

        if result is None:
            # Queue was empty, yield control to event loop briefly
            # 0.01s (10ms) allows other async tasks to run without blocking
            await asyncio.sleep(0.01)
            continue

        msg_type, data = result

        if msg_type == 'item':
            yield data
        elif msg_type == 'error':
            raise data
        elif msg_type == 'done':
            break

    # Wait for thread to finish (with timeout to avoid hanging)
    thread.join(timeout=1)


async def async_stream_wrapper_with_heartbeat(
    loop: asyncio.AbstractEventLoop,
    generator_func: Callable[..., Generator],
    *args: Any,
    heartbeat_interval: int = 10,
    **kwargs: Any
) -> AsyncGenerator[Any, None]:
    """
    Wrap a synchronous generator for async iteration with heartbeat support.

    Similar to async_stream_wrapper, but additionally yields heartbeat messages
    when no data has been received for heartbeat_interval seconds. This keeps
    HTTP connections alive during long-running operations.

    Heartbeat messages: {'type': 'heartbeat'}

    Args:
        loop: The asyncio event loop
        generator_func: A function that returns a generator
        *args: Positional arguments to pass to generator_func
        heartbeat_interval: Seconds between heartbeats (default: 10)
        **kwargs: Keyword arguments to pass to generator_func

    Yields:
        Items from the generator, interspersed with heartbeat dicts

    Note:
        The heartbeat timer resets whenever an item is received, so heartbeats
        only occur during genuine periods of inactivity.
    """
    result_queue: queue.Queue = queue.Queue()

    def run_generator():
        """Background thread: runs generator and puts items to queue."""
        try:
            for item in generator_func(*args, **kwargs):
                result_queue.put(('item', item))
        except Exception as e:
            result_queue.put(('error', e))
        finally:
            result_queue.put(('done', None))

    # Start generator in background thread
    thread = threading.Thread(target=run_generator, daemon=True)
    thread.start()

    # Track last activity for heartbeat timing
    last_activity = time.time()

    # Yield items as they come
    while True:
        current_time = time.time()

        # Send heartbeat if no activity for heartbeat_interval seconds
        if current_time - last_activity >= heartbeat_interval:
            yield {'type': 'heartbeat'}
            last_activity = current_time

        # Non-blocking check with timeout
        def get_with_timeout():
            try:
                return result_queue.get(timeout=0.1)  # 100ms polling interval
            except queue.Empty:
                return None

        result = await loop.run_in_executor(None, get_with_timeout)

        if result is None:
            # Queue was empty, yield control to event loop
            await asyncio.sleep(0.01)
            continue

        msg_type, data = result

        if msg_type == 'item':
            yield data
            last_activity = time.time()  # Reset heartbeat timer on activity
        elif msg_type == 'error':
            raise data
        elif msg_type == 'done':
            break

    # Wait for thread to finish
    thread.join(timeout=1)
