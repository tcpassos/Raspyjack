import traceback
try:
    from openai import OpenAI # type: ignore
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

    def _run_openai(self, instructions: str, user_prompt: str, wctx=None) -> str:
        """Run an OpenAI request while optionally showing a waiting dialog in the UI.

        Args:
            instructions: system-level instructions for the model
            user_prompt: the user-supplied prompt/input
            wctx: optional WidgetContext to display a waiting dialog (from ui.widgets)
        """
        if not self.is_ready():
            return "[OPENAI] OpenAI client not initialized."
        wait_handle = None
        try:
            if wctx is not None:
                try:
                    from ui.widgets import dialog_wait
                    wait_handle = dialog_wait(wctx, "Analyzing with AI...")
                except Exception:
                    wait_handle = None
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=user_prompt
            )
            return response.output_text
        except Exception as e:
            print("--- OpenAI API Error ---")
            traceback.print_exc()
            print("------------------------")
            return f"[OPENAI] OpenAI API error: {e}"
        finally:
            if wait_handle is not None:
                try:
                    from ui.widgets import dialog_wait_close
                    dialog_wait_close(wctx, wait_handle)
                except Exception:
                    pass

    def analyze_file(self, file_to_analyze: str, prompt_content: str, wctx=None) -> str:
        instructions = (
            "You are a senior penetration tester analyzing data from a physical implant. "
            "Your goal is to identify key findings and actionable insights from the provided content. "
            "Provide a concise, direct, multi-line report."
            f"Do not include disclaimers. Respond in the user-specified language ({self.language})."
        )
        # Read the content of the file to analyze
        try:
            with open(file_to_analyze, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return f"[OPENAI] Failed to read file '{file_to_analyze}': {e}"
        
        # Combine provided prompt content and file content
        user_prompt = f"{prompt_content}\n\n--- FILE CONTENT ---\n{content}\n--- END OF CONTENT ---"
        
        return self._run_openai(instructions, user_prompt, wctx=wctx)

    def prompt(self, prompt: str, wctx=None) -> str:
        instructions = f"You are an on-device assistant. Respond concisely and directly. Language: {self.language}."
        return self._run_openai(instructions, prompt, wctx=wctx)
