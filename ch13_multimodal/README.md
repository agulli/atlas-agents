# Chapter 13 — Multimodal and Voice Agents

> **Atlas v0.13** — a document analyst that **routes each input type to the model best at it** (images → Claude vision, PDFs → Gemini native PDF, text → Claude), plus real-time phone voice agents.

## TL;DR

Real inputs aren't only text: screenshots, scanned PDFs, slide decks, phone calls. Two ideas cover most of it:

1. **Modality routing**: detect the input type and send it to the model/pipeline that handles it best, with a fallback.
2. **Streaming voice bridges**: a phone call is a WebSocket of audio frames. Convert codecs and sample rates in both directions and let a realtime model (OpenAI Realtime or Gemini Live) handle speech-to-speech, including callers interrupting mid-sentence (barge-in).

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Modality router** | `image` → Claude vision, `pdf` → Gemini 2.5 Flash, `text` → Claude. | `route_and_analyze()` |
| **Vision input** | Base64-encode the image with its MIME type in a content block. | `analyze_image()` |
| **Fallback path** | If Gemini isn't available, extract PDF text with `pdftotext` and send it to Claude. | `analyze_pdf_fallback()` |
| **Page-as-image** | For visual PDFs (scans, slides, financial tables), render each page to PNG and use vision, then synthesize. | `online/batch_pdf_analyst.py` |
| **Visual diffing** | Compare a design export with a rendered screenshot and get concrete CSS fixes. | `online/screenshot_debugger.py` |
| **Telephony audio** | Twilio streams PCMU @ 8 kHz. OpenAI Realtime wants PCM16 @ 24 kHz, and Gemini Live wants PCM16 @ 16 kHz. Resample both ways. | `online/voice_agent_twilio.py`, `online/gemini_live_agent.py` |
| **Barge-in** | When the caller interrupts, cancel the model's current response (OpenAI: explicit cancel; Gemini: server sets `interrupted=True`). | voice agents |
| **Voice tool calls** | Realtime models can call tools mid-conversation. The server executes them and returns results. | `_execute_tool()` |

## Files

| File | What it shows |
|---|---|
| `multimodal_agent.py` | The chapter project: image/PDF/text routing with fallback. |
| `online/batch_pdf_analyst.py` | Page-by-page vision analysis of complex PDFs (needs poppler). |
| `online/screenshot_debugger.py` | Expected vs. actual screenshot → list of CSS fixes. |
| `online/voice_agent_twilio.py` | FastAPI bridge: Twilio Media Stream ↔ OpenAI Realtime API. |
| `online/gemini_live_agent.py` | The same bridge using the Gemini Live API. |

## What needs to be done

- [ ] `pip install anthropic google-genai`, and set `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY`.
- [ ] Analyze a screenshot with an error in it, a PDF report, and a text file of notes.
- [ ] Remove `GOOGLE_API_KEY` and confirm the PDF fallback path still works.
- [ ] Run `batch_pdf_analyst.py` on a slide deck and compare it with the text-extraction result.
- [ ] (Stretch) Expose the voice agent with a tunnel, point a Twilio number's Voice URL at `/twiml`, and call it.

## Run it

```bash
cd ch13_multimodal
python multimodal_agent.py image screenshot.png "What errors do you see?"
python multimodal_agent.py pdf   report.pdf     "Summarize the key findings"
python multimodal_agent.py text  notes.txt      "What are the action items?"

uvicorn online.voice_agent_twilio:app --port 8080   # or gemini_live_agent:app
# Python 3.13+: pip install audioop-lts
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ⚠️ Partly local.** Images and text work on Gemma 4, which has vision. PDFs take the `pdftotext` fallback path. **The voice agents are cloud-only**: they depend on OpenAI Realtime / Gemini Live speech-to-speech streaming APIs, and Ollama has no equivalent.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=gemma4-longctx`. Leave `GOOGLE_API_KEY` **unset** so PDFs skip Gemini.

```bash
pip install anthropic python-dotenv pdf2image
# PDF tools (poppler): macOS: brew install poppler   Linux: sudo apt-get install poppler-utils
```

Check that the endpoint accepts images (Gemma 4 vision through the Anthropic-compatible API):

```bash
IMG=$(base64 < some_screenshot.png | tr -d '\n')
curl -s http://localhost:11434/v1/messages -H 'content-type: application/json' -H 'x-api-key: ollama' -d "{
  \"model\":\"gemma4-longctx\",\"max_tokens\":100,
  \"messages\":[{\"role\":\"user\",\"content\":[
    {\"type\":\"image\",\"source\":{\"type\":\"base64\",\"media_type\":\"image/png\",\"data\":\"$IMG\"}},
    {\"type\":\"text\",\"text\":\"Describe this image in one sentence.\"}]}]}" | head -c 400; echo
```

### Commands

```bash
python ch13_multimodal/multimodal_agent.py image screenshot.png "What errors do you see?"
python ch13_multimodal/multimodal_agent.py pdf   report.pdf     "Summarize the key findings"   # Gemini fails fast → pdftotext → Gemma
python ch13_multimodal/multimodal_agent.py text  notes.txt      "What are the action items?"

python ch13_multimodal/online/batch_pdf_analyst.py slides.pdf "Summarize each slide in one sentence"   # each page → image → Gemma vision
python ch13_multimodal/online/screenshot_debugger.py expected.png actual.png
```

### What to expect on Gemma 4

- For a **text-heavy PDF**, the fallback (`pdftotext` → Gemma) works well. For a **visual PDF** (slides, scans, charts), use `batch_pdf_analyst.py`: it sends each page as an image, so the layout survives.
- Gemma reads screenshots, error dialogs, and charts well. Pixel-exact measurements in `screenshot_debugger.py` (padding in px, hex colors) are less precise than with frontier models. Treat its CSS fixes as hints.
- Each page image costs about 1k+ tokens of context, so keep `MAX_PAGES` small locally.
- `voice_agent_twilio.py` / `gemini_live_agent.py`: no local path. Read them for the audio-pipeline concepts.

### Troubleshooting

- **The image `curl` returns an error about content type**: update Ollama and confirm `ollama show gemma4-longctx` lists `vision`.
- **`pdftotext: command not found`**: install poppler (above).

## Production notes

- Images and PDF pages are expensive in tokens. Cap page counts (`MAX_PAGES`) and resolution.
- Voice latency budgets are tight (a few hundred ms). Keep tools fast or answer with filler speech first.
- `audioop` was removed in Python 3.13, so install `audioop-lts`.

## Takeaways

1. Route by modality and don't assume one model is best at everything.
2. When text extraction loses the layout, send the page as an image.
3. Voice agents are mostly an audio pipeline problem: codecs, sample rates, streaming, interruption.

**Prev:** [Ch. 12](../ch12_sandboxes/README.md) · **Next:** [Chapter 14 — Guardrails and Agent Safety](../ch14_guardrails/README.md)
