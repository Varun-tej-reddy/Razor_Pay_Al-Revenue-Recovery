"""
Core Google Gemini LLM Client for Revenue Recovery Multi-Agent Swarm
Connects directly to Gemini 3.6 Flash for high-speed, transaction-grounded inference.
"""

import os
import json
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"]

def get_gemini_api_key() -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key and key != "your_gemini_api_key_here":
        return key.strip()
    return None

def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    model: Optional[str] = None,
    response_mime_type: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Invokes the Google Gemini REST API with active key and model fallbacks.
    Returns dict:
      {
        "success": bool,
        "text": str,
        "latency_ms": int,
        "model": str,
        "error": Optional[str]
      }
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return {
            "success": False,
            "text": "",
            "latency_ms": 0,
            "model": "none",
            "error": "GEMINI_API_KEY not configured or placeholder"
        }

    target_models = [model] if model else FALLBACK_MODELS
    last_error = None

    for target_model in target_models:
        if not target_model:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 1024,
            }
        }
        
        if response_mime_type:
            payload["generationConfig"]["responseMimeType"] = response_mime_type

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        start_time = time.time()
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - start_time) * 1000)
                
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if "text" in p)
                    return {
                        "success": True,
                        "text": text.strip(),
                        "latency_ms": latency,
                        "model": target_model,
                        "error": None
                    }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {e.code}: {err_body}"
        except Exception as e:
            last_error = str(e)

    return {
        "success": False,
        "text": "",
        "latency_ms": 0,
        "model": target_models[0],
        "error": last_error or "Unknown error calling Gemini API"
    }

def clean_json_response(text: str) -> Dict[str, Any]:
    """
    Extracts and parses JSON from LLM output, handling markdown code blocks if present.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
    return {}
