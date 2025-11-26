# Local C-Coding Agents (vLLM + Python Test Runner)

Tento projekt využíva lokálny vLLM server ako OpenAI-kompatibilný backend a skupinu AI agentov, ktorí automaticky generujú, kompilujú a opravujú C program, až kým neprejde všetkými Python testami (`run-tests.py`).  
Ak sa `actual-stdout` nezhoduje s `stdout`, agent kód upraví a cyklus zopakuje.

---

## 🔧 Požiadavky
- Linux
- NVIDIA GPU
- Python 3.10+
- gcc
- vLLM + kompatibilný model (napr. Qwen2.5 Coder 3B Instruct)

---

## 🚀 Spustenie vLLM servera

Vytvorenie prostredia:

```bash
mkdir -p ~/ai/vllm_server
cd ~/ai/vllm_server
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install vllm openai
```

Spustenie servera:

```bash
vllm serve Qwen/Qwen2.5-Coder-3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.8 \
  --api-key token-abc123
```

V agents_vllm.py uprav tieto cesty:

ROOT_DIR = "/absolutna/cesta/kde/sa/ulozi/main.c"
TESTS_DIR = "/absolutna/cesta/kde/su/testy/"
MODEL_NAME = "Qwen/Qwen2.5-Coder-3B-Instruct"

▶️ Spustenie agentov

```bash
cd <repo>
python3 -m venv venv
source venv/bin/activate
pip install openai
python3 agents_vllm.py
```

Agent automaticky vykoná:

    vygeneruje main.c,

    uloží ho do ROOT_DIR,

    skompiluje cez gcc,

    spustí run-tests.py,

    porovná očakávaný výstup,

    opravuje kód, kým všetky testy neprejdú.

🧩 Zmena zadania

Text úlohy je definovaný v súbore:
```bash
PROBLEM = "..."
```
Prepíš obsah a agent vytvorí nový program.

🎉 Výsledok

Keď testy prejdú:
🎉 VŠETKY TESTY PREŠLI
Hotový skompilovaný program main sa nachádza v ROOT_DIR.



