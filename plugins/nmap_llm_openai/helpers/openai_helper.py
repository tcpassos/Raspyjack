try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class OpenAIHelper:
    def __init__(self, api_key: str, language: str = "en", model: str = "gpt-5-nano"):
        self.api_key = api_key
        self.language = language
        self.model = model
        self.client = None
        if OpenAI and api_key:
            try:
                self.client = OpenAI(api_key=api_key)
            except Exception:
                self.client = None

    def is_ready(self):
        return self.client is not None

    def analyze_nmap_scan(self, scan_text: str, nmap_command: str = "") -> str:
        if not self.is_ready():
            return "[ERROR] OpenAI client not initialized."
        prompt = (
            f"This is my output from my NMAP scan {nmap_command}. "
            f"Give detailed analysis to me in bullet points, and say any security feedback if necessary. "
            f"Respond in {self.language}.\nScan output:\n{scan_text}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=256,
                frequency_penalty=0.0
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[ERROR] OpenAI API error: {e}"

    def prompt(self, prompt: str) -> str:
        if not self.is_ready():
            return "[ERROR] OpenAI client not initialized."
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=256,
                frequency_penalty=0.0
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[ERROR] OpenAI API error: {e}"
