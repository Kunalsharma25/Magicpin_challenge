import os
import json
from urllib import request as urlrequest, error as urlerror
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self, openai_key: str = None, model: str = "gpt-4o-mini"):
        self.openai_key = openai_key or os.environ.get("OPENAI_API_KEY") or ""
        self.groq_key = os.environ.get("GROQ_API_KEY") or ""
        self.gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        """
        Primary LLM execution via OpenAI (gpt-4o-mini) with temperature=0 (deterministic).
        Falls back to Groq, Gemini, or structured mock completion.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        # 1. Try OpenAI Primary (gpt-4o-mini)
        if self.openai_key:
            try:
                body = json.dumps({
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 1000
                }).encode("utf-8")

                req = urlrequest.Request(
                    "https://api.openai.com/v1/chat/completions",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )

                with urlrequest.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"[LLMClient Warning] OpenAI API call failed: {e}")

        # 2. Try Groq Fallback
        if self.groq_key:
            try:
                body = json.dumps({
                    "model": "llama3-8b-8192",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 1000
                }).encode("utf-8")

                req = urlrequest.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {self.groq_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "magicpin-bot/1.0"
                    },
                    method="POST"
                )

                with urlrequest.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"[LLMClient Warning] Groq Fallback API call failed: {e}")

        # 3. Try Gemini Fallback
        if self.gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.gemini_key)
                resp = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=f"{system_prompt}\n\n{user_prompt}"
                )
                return resp.text
            except Exception as e:
                print(f"[LLMClient Warning] Gemini Fallback call failed: {e}")

        # 4. Emergency fallback
        return self._mock_completion(user_prompt)

    def _mock_completion(self, user_prompt: str) -> str:
        return json.dumps({
            "body": "Hi, notice from our records your recent activity. Reply YES to confirm or connect.",
            "cta": "binary",
            "send_as": "vera",
            "rationale": "Generated via default fallback."
        })

llm_client = LLMClient()
