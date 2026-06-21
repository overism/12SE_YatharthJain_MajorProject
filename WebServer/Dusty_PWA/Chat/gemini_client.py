"""
Chat/gemini_client.py  –  Dusty Gemini wrapper
Improvements:
  - Single lazy-initialised client (avoids re-authenticating every call)
  - Retry with exponential backoff on transient errors
  - Clean JSON extraction that handles all fence variants
  - Descriptive RuntimeError messages surfaced to the user
  - Model name configurable via GEMINI_MODEL env var
"""

from __future__ import annotations
import json
import os
import re
import time
import traceback

from dotenv import load_dotenv

load_dotenv()

# ── CONFIGURATION ─────────────────────────────────────────────────
DEFAULT_MODEL   = "gemini-2.5-flash-lite"
MAX_RETRIES     = 3
RETRY_DELAY_S   = 1.5     # doubled on each retry
REQUEST_TIMEOUT = 60      # seconds

# ── LAZY CLIENT CACHE ─────────────────────────────────────────────
_client_cache: tuple[str, object] | None = None


def _get_client() -> tuple[str, object]:
    """Return (client_type, client), initialised once per process."""
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )

    # Try the modern google-genai SDK first
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        _client_cache = ("modern", client)
        return _client_cache
    except ImportError:
        pass

    # Fall back to legacy google-generativeai
    try:
        import google.generativeai as genai_legacy
        genai_legacy.configure(api_key=api_key)
        _client_cache = ("legacy", genai_legacy)
        return _client_cache
    except ImportError:
        raise RuntimeError(
            "No Gemini SDK found. Run: pip install google-genai  "
            "(or pip install google-generativeai for the legacy SDK)."
        )


def _call_with_retry(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) up to MAX_RETRIES times on transient errors."""
    delay = RETRY_DELAY_S
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            # Only retry on rate-limit / timeout / server errors
            transient = any(k in msg for k in (
                "429", "500", "503", "timeout", "rate", "quota",
                "resource_exhausted", "unavailable",
            ))
            if not transient or attempt == MAX_RETRIES:
                break
            print(f"[GEMINI] Attempt {attempt} failed ({exc}). Retrying in {delay}s…")
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"Gemini API error: {last_exc}") from last_exc


# ── PUBLIC API ────────────────────────────────────────────────────

def ask_gemini(
    prompt: str,
    temperature: float = 0.65,
    max_output_tokens: int = 4096,
) -> str:
    """
    Send a text prompt to Gemini and return the response string.
    Raises RuntimeError with a clear message on failure.
    """
    client_type, client = _get_client()
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    def _call():
        if client_type == "legacy":
            model = client.GenerativeModel(
                model_name=model_name,
                generation_config={
                    "temperature":        temperature,
                    "top_p":              0.9,
                    "max_output_tokens":  max_output_tokens,
                },
            )
            resp = model.generate_content(
                prompt,
                request_options={"timeout": REQUEST_TIMEOUT},
            )
            text = getattr(resp, "text", None)
            if not text:
                # Surface the finish reason if available
                reason = ""
                try:
                    reason = resp.candidates[0].finish_reason
                except Exception:
                    pass
                raise RuntimeError(
                    f"Gemini returned an empty response (finish_reason={reason}). "
                    "The prompt may have been blocked by safety filters."
                )
            return text.strip()

        # Modern SDK
        try:
            from google.genai import types
            cfg = types.GenerateContentConfig(
                temperature=temperature,
                top_p=0.9,
                max_output_tokens=max_output_tokens,
            )
            resp = client.models.generate_content(
                model=model_name, contents=prompt, config=cfg
            )
        except Exception:
            # Config not supported by this SDK version — call without it
            resp = client.models.generate_content(
                model=model_name, contents=prompt
            )

        text = getattr(resp, "text", None)
        if not text:
            raise RuntimeError(
                "Gemini returned an empty response. "
                "The prompt may have been blocked by safety filters."
            )
        return text.strip()

    try:
        return _call_with_retry(_call)
    except RuntimeError:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise RuntimeError(f"Unexpected error calling Gemini: {exc}") from exc


def ask_gemini_json(
    prompt: str,
    temperature: float = 0.40,
    max_output_tokens: int = 4096,
) -> dict | list:
    """
    Ask Gemini for a JSON response and parse it.
    Handles markdown fences, leading 'json' labels, and whitespace.
    Raises RuntimeError if the response cannot be parsed.
    """
    raw = ask_gemini(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
    return _parse_json(raw)

def _fix_latex_backslashes(text: str) -> str:
    VALID_SINGLE = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't'}
    result: list[str] = []
    in_string = False
    i, n = 0, len(text)

    while i < n:
        ch = text[i]

        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        # ── inside a JSON string value ──────────────────────────
        if ch == '\\':
            if i + 1 < n:
                nc = text[i + 1]
                if nc in VALID_SINGLE:
                    # Valid single-char escape — keep
                    result.append(ch); result.append(nc); i += 2
                elif (nc == 'u' and i + 5 < n
                      and all(c in '0123456789abcdefABCDEF'
                              for c in text[i + 2:i + 6])):
                    # Valid \uXXXX — keep
                    result.extend(text[i:i + 6]); i += 6
                else:
                    # LaTeX or other invalid escape — double the backslash
                    result.append('\\'); result.append('\\'); i += 1
            else:
                result.append('\\'); result.append('\\'); i += 1
        elif ch == '"':
            result.append(ch)
            in_string = False
            i += 1
        else:
            result.append(ch)
            i += 1

    return ''.join(result)


def _parse_json(text: str) -> dict | list:
    """Strip markdown fences and parse JSON. Raises RuntimeError on failure."""
    cleaned = text.strip()

    # Strip opening fence from the VERY START only (not every line — avoid
    # corrupting question text that legitimately starts with backticks)
    if cleaned.startswith('```'):
        first_newline = cleaned.find('\n')
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:].strip()
        else:
            cleaned = cleaned.lstrip('`')
            if cleaned.lower().startswith('json'):
                cleaned = cleaned[4:].strip()

    # Strip closing fence from the VERY END only
    if cleaned.endswith('```'):
        last_fence = cleaned.rfind('\n```')
        if last_fence != -1:
            cleaned = cleaned[:last_fence].strip()
        else:
            cleaned = cleaned[:-3].strip()

    # Some models prefix with 'json\n' after stripping
    if cleaned.lower().startswith('json\n'):
        cleaned = cleaned[5:].strip()

    # 1. Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Fix LaTeX / unescaped backslashes (common in maths quizzes)
    latex_fixed = _fix_latex_backslashes(cleaned)
    if latex_fixed != cleaned:
        try:
            return json.loads(latex_fixed)
        except json.JSONDecodeError:
            cleaned = latex_fixed   # carry fixed version forward

    # 3. Extract first balanced JSON object or array
    extracted = _extract_balanced_json(cleaned)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    # 4. Minor structural repairs
    repaired = _repair_json_text(cleaned)
    if repaired != cleaned:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    raise RuntimeError(
        f"Gemini did not return valid JSON. "
        f"Raw response (first 300 chars): {text[:300]!r}"
    )


def _extract_balanced_json(text: str) -> str | None:
    """Extract the first balanced JSON object or array from text."""
    start_chars = {'{': '}', '[': ']'}
    
    for i, ch in enumerate(text):
        if ch not in start_chars:
            continue
        
        stack = [ch]
        in_string = False
        escaped = False
        
        for j in range(i + 1, len(text)):
            c = text[j]
            
            if in_string:
                if escaped:
                    escaped = False
                elif c == '\\':
                    escaped = True
                elif c == '"':
                    in_string = False
                continue
            
            if c == '"':
                in_string = True
                continue
            if c in start_chars:
                stack.append(c)
                continue
            if c in ('}', ']'):
                if not stack:
                    break
                opener = stack.pop()
                if start_chars[opener] != c:
                    break
                if not stack:
                    return text[i:j + 1]
    
    return None


def _repair_json_text(text: str) -> str:
    """Apply lightweight repairs to broken JSON."""
    # Remove stray comments
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Fix unescaped backslashes inside string values (common with LaTeX output).
    # Replace lone backslashes that aren't part of a valid JSON escape sequence.
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)

    # Fix common issues
    if text.count('"') % 2 == 1:
        text += '"'

    open_braces = text.count('{') - text.count('}')
    if open_braces > 0:
        text += '}' * open_braces

    open_brackets = text.count('[') - text.count(']')
    if open_brackets > 0:
        text += ']' * open_brackets

    return text
