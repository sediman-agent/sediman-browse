# Using Sediman with Ollama

Run Sediman entirely locally with [Ollama](https://ollama.com) — no API keys required.

## 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

## 2. Pull a Model

Sediman defaults to `qwen3` for the Ollama provider:

```bash
ollama pull qwen3
```

Other tested models:

| Model        | Pull Command            | Notes                        |
|--------------|-------------------------|------------------------------|
| Qwen 3       | `ollama pull qwen3`     | Default — good balance       |
| Llama 3.3    | `ollama pull llama3.3`  | Strong reasoning             |
| Gemma 3      | `ollama pull gemma3`    | Lightweight                  |
| Mistral      | `ollama pull mistral`   | Fast responses               |

## 3. Start the Ollama Server

```bash
ollama serve
```

Runs on `http://localhost:11434` by default.

## 4. Run Sediman with Ollama

### One-shot task

```bash
sediman run --provider ollama "check the weather in New York"
```

### Specify a different model

```bash
sediman run --provider ollama --model llama3.3 "summarize the top Hacker News posts"
```

### Interactive chat

```bash
sediman chat --provider ollama
```

### API server

```bash
sediman serve --provider ollama --port 8000
```

## 5. No Environment Variables Needed

When using `--provider ollama`, Sediman does **not** require `OPENAI_API_KEY`. The `OPENAI_API_KEY` line in `.env` can be left blank or omitted entirely.

## Troubleshooting

| Symptom                          | Fix                                                    |
|----------------------------------|--------------------------------------------------------|
| `connection refused`             | Make sure `ollama serve` is running                    |
| Model not found                  | Run `ollama pull <model>` first                        |
| Slow responses                   | Try a smaller model or check GPU memory                |
| JSON parse errors in browser use | Use `qwen3` or `llama3.3` — some models struggle with structured output |

## Custom Base URL

If Ollama runs on a different host or port:

```bash
sediman run --provider ollama --base-url http://192.168.1.50:11434/v1 "your task"
```
