from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None


class RateLimitExceeded(Exception):
    pass


class RateLimitedLLM:
    def __init__(self, model_name: str, rpm: int, provider: str = "google",
                 **kwargs):
        if provider == "google" and ChatGoogleGenerativeAI:
            self._impl = ChatGoogleGenerativeAI(model=model_name, **kwargs)
        elif provider == "groq" and ChatGroq:
            self._impl = ChatGroq(model=model_name, **kwargs)
        else:
            raise ValueError(f"Provider {provider} not available")

        self.rpm = rpm
        self._timestamps = deque()

    def invoke(self, payload: Dict[str, Any]):
        now = time.time()
        while self._timestamps and now - self._timestamps[0] > 60:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.rpm:
            raise RateLimitExceeded(
                f"{self._impl.model} exceeded {self.rpm} RPM"
            )

        self._timestamps.append(now)
        return self._impl.invoke(payload)

    def with_structured_output(self, schema):
        return StructuredRateLimitedWrapper(self, schema)


class StructuredRateLimitedWrapper:
    def __init__(self, rate_limited_llm: RateLimitedLLM, schema):
        self.rate_limited_llm = rate_limited_llm
        self.structured = rate_limited_llm._impl.with_structured_output(schema)

    def invoke(self, payload: Dict[str, Any]):
        now = time.time()
        timestamps = self.rate_limited_llm._timestamps
        while timestamps and now - timestamps[0] > 60:
            timestamps.popleft()

        if len(timestamps) >= self.rate_limited_llm.rpm:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.rate_limited_llm.rpm} RPM"
            )

        self.rate_limited_llm._timestamps.append(now)
        return self.structured.invoke(payload)


class FailoverLLM:
    def __init__(self, backends):
        self.backends = backends

    def invoke(self, payload: Dict[str, Any]):
        last_exc = None
        for backend in self.backends:
            try:
                return backend.invoke(payload)
            except RateLimitExceeded as e:
                last_exc = e
                print(f"[RATE_LIMIT] {e}, trying next backend...")
                continue

        if last_exc:
            raise last_exc
        raise RuntimeError("No backends configured")

    def with_structured_output(self, schema):
        return StructuredFailoverWrapper(self, schema)


class StructuredFailoverWrapper:
    def __init__(self, failover_llm: FailoverLLM, schema):
        self.failover_llm = failover_llm
        self.structured_backends = []
        for backend in failover_llm.backends:
            if hasattr(backend, 'with_structured_output'):
                structured_backend = backend.with_structured_output(schema)
                self.structured_backends.append(structured_backend)

    def invoke(self, payload: Dict[str, Any]):
        last_exc = None
        for backend in self.structured_backends:
            try:
                return backend.invoke(payload)
            except RateLimitExceeded as e:
                last_exc = e
                print(f"[RATE_LIMIT] {e}, trying next backend...")
                continue

        if last_exc:
            raise last_exc
        raise RuntimeError("No structured backends available")
