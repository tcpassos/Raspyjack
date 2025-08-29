# Nmap LLM OpenAI Plugin

> ⚠️ **Attention:** On the first startup after enabling the plugin, the system may take several minutes as Python dependencies are installed automatically. Please wait until the process completes before using all features!

> ℹ️ **Note:** After the plugin is initialized, an entry will be created in `plugins_conf.json`. You must edit this file and set the `api_key` property with your OpenAI API key to enable all features.

This plugin integrates OpenAI's language models with Nmap scan results, providing automated and on-demand AI-powered analysis for security assessments.

## Features
- **Manual Analysis**: Select any Nmap scan text file and process it with OpenAI. The AI result is saved in `loot/Nmap` and displayed in a scrollable text widget.
- **Automatic Analysis**: If enabled in the plugin options, every completed Nmap scan is automatically analyzed by the AI. You are prompted to open the result after each scan.
- **Configurable Model and Language**: Choose the OpenAI model (default: `gpt-5-nano`) and response language in the plugin settings.
- **API Key Management**: Enter your OpenAI API key in the plugin configuration to enable all features.
- **Dependency Management**: The plugin checks and installs the `openai` Python package automatically if missing.
- **PROMPT_OPENAI Executable**: Use the `bin/PROMPT_OPENAI` script to send any prompt to OpenAI, saving the result in `loot/AI` and setting the output path in the `AI_OUTPUT_PATH` environment variable.
- **Shared Helper**: All OpenAI logic is centralized in `helpers/openai_helper.py` for use by both the plugin and executables.

## Usage
1. **Configure the Plugin**:
   - Set your OpenAI API key, preferred language, and model in the plugin options.
   - Optionally enable automatic analysis of Nmap scans.
2. **Manual Analysis**:
   - Open the plugin menu and select "Analyze Nmap Scan File".
   - Choose a scan file from `loot/Nmap`. The AI result will be saved and displayed.
3. **Automatic Analysis**:
   - When enabled, every scan triggers AI analysis. You will be prompted to view the result.
4. **Command-Line AI Prompt**:
   - Run `bin/PROMPT_OPENAI <prompt>` to send any text to OpenAI. The result is saved in `loot/AI` and the path is set in `AI_OUTPUT_PATH`.

## Requirements
- Python 3.x
- OpenAI API key
- Internet connection for API calls

## File Structure
```
nmap_llm_openai/
  README.md
  _impl.py                # Main plugin implementation
  bin/
    PROMPT_OPENAI         # Command-line AI prompt tool
  helpers/
    openai_helper.py      # Shared OpenAI logic
```

## Notes
- The plugin will attempt to install the `openai` package automatically if not present.
- All AI results are saved with timestamps for easy tracking.
- The plugin is designed for integration with the Raspyjack menu and widget system.

---
Developed for Raspyjack - Automated Nmap AI Analysis
