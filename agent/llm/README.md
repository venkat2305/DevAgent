# LLM Module Refactoring

## Structure

The large `graph.py` file has been broken down into modular components:

### Files:
- **`graph.py`** - Main orchestration, builds the StateGraph and public API
- **`helpers.py`** - Utility functions (job dir, JSON serialization, checkpointer, packaging)
- **`llm_wrappers.py`** - Rate limiting and failover for LLM providers
- **`nodes.py`** - Individual node functions for the state graph
- **`schema.py`** - Data models (unchanged)
- **`tools.py`** - Tool definitions (unchanged)

### Rate Limiting Features:
- `RateLimitedLLM`: Enforces RPM limits per model using sliding window
- `FailoverLLM`: Automatically switches to backup models when rate limits hit
- Supports multiple providers (Google Gemini, Groq, etc.)

### Usage Example:
```python
flash = RateLimitedLLM("gemini-2.5-flash", rpm=10, temperature=0.1)
pro = RateLimitedLLM("gemini-2.5-pro", rpm=5, temperature=0.1)
groq = RateLimitedLLM("llama-3.1-70b-versatile", rpm=100, 
                      provider="groq", temperature=0.1)
model = FailoverLLM([flash, groq, pro])
```

## Benefits:
- Clean separation of concerns
- Rate limiting prevents API quota exhaustion  
- Automatic failover to backup models
- Extensible to new providers
- Reduced file complexity
