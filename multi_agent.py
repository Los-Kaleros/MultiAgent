import os
import re
import subprocess
from openai import OpenAI

print(">>> agents_vllm.py sa NAČÍTAL")

# ==========================
# KONFIGURÁCIA
# ==========================

# ROOT_DIR = kde bude main.c a binárka ./main
ROOT_DIR = ""

# TESTS_DIR = priečinok s run-tests.py a test-* adresármi
TESTS_DIR = os.path.join(ROOT_DIR, "tests")

SOURCE_NAME = "main.c"   # názov C súboru
BINARY_NAME = "main"     # názov binárky (./main)
RUN_TESTS_SCRIPT = "run-tests.py"

# maximálny počet iterácií (generovanie + opravy)
MAX_ITERATIONS = 10

# Názov modelu, ktorý beží vo vLLM serveri
MODEL_NAME = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"

# Zadanie – histogram
PROBLEM = """ """

# Stručné pripomenutie zadania pre opravné iterácie
SHORT_SPEC_HINT = ()

# ==========================
# PRIPOJENIE NA vLLM
# ==========================

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="token-abc123",
)

# ==========================
# POMOCNÉ FUNKCIE
# ==========================

def truncate(text: str, max_chars: int) -> str:
    """Oreže text na max_chars znakov, zvyšok označí ako TRUNCATED."""
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[TRUNCATED]...\n"


def call_agent(role: str, goal: str, message: str) -> str:
    """
    Zavolá jedného agenta s danou rolou a cieľom cez vLLM server.
    """
    print(f">>> Volám agenta: {role}")
    system_prompt = (
        f"Si agent s rolou: {role}. Tvoj cieľ: {goal}.\n"
        "Pri odpovedi dodrž tieto pravidlá:\n"
        "- Vráť len čistý C kód (žiadny Markdown, žiadne ``` bloky).\n"
        "- Nepíš žiadne vysvetlenia, komentáre ani text mimo C kódu.\n"
    )
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.1,   # menej kreativity, viac stability
        top_p=0.9,
        max_tokens=1200,
    )
    return completion.choices[0].message.content


def extract_c_code(response: str) -> str:
    """
    Ak LLM vráti kód v ```c ... ``` bloku, vytiahne len obsah.
    Inak vráti celý text ako kód.
    """
    fence_match = re.search(
        r"```(?:c|C|cpp|C\+\+)?\s*(.*?)```",
        response,
        re.DOTALL
    )
    if fence_match:
        code = fence_match.group(1).strip()
        print(">>> Z odpovede som vytiahol kód z ``` blokov.")
        return code

    if "```" in response:
        parts = response.split("```")
        if len(parts) >= 3:
            code = parts[1]
            print(">>> Fallback: vytiahol som druhý úsek medzi ```.")
            return code.strip()

    print(">>> Celá odpoveď sa berie ako kód (žiadne rozpoznané ``` bloky).")
    return response.strip()


def save_code_to_root_dir(code: str) -> str:
    """
    Uloží C kód do ROOT_DIR/main.c (SOURCE_NAME).
    Vráti absolútnu cestu k uloženému súboru.
    """
    os.makedirs(ROOT_DIR, exist_ok=True)
    source_path = os.path.join(ROOT_DIR, SOURCE_NAME)
    with open(source_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f">>> Kód uložený do: {source_path}")
    return source_path


def compile_c_code() -> tuple[bool, str]:
    """
    Skúsi skompilovať main.c -> main v ROOT_DIR pomocou gcc.
    Vráti (success, stderr_text).
    """
    print(">>> Kompilujem C kód pomocou gcc...")
    proc = subprocess.run(
        ["gcc", "-Wall", "-Wextra", "-std=c99", SOURCE_NAME, "-o", BINARY_NAME],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    success = proc.returncode == 0
    return success, proc.stderr


def run_python_tests() -> tuple[bool, str, str]:
    """
    Spustí python testy: python3 run-tests.py ../main v TESTS_DIR.

    Vráti:
      - success (bool)
      - stdout (str)
      - stderr (str)
    """
    print(">>> Spúšťam python testy (run-tests.py)...")
    try:
        proc = subprocess.run(
            ["python3", RUN_TESTS_SCRIPT, f"../{BINARY_NAME}"],
            cwd=TESTS_DIR,
            capture_output=True,
            text=True,
            timeout=5.0,  # 5 sekúnd na všetky testy
        )
        success = proc.returncode == 0
        return success, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        print("!!! run-tests.py prekročil časový limit (timeout)")
        stdout = e.stdout or ""
        stderr = (e.stderr or "") + "\n[TIMEOUT: run-tests.py alebo ./main sa neukončili v limite]"
        return False, stdout, stderr


def collect_stdout_differences(max_chars: int = 400):
    """
    Prejde všetky podpriečinky v TESTS_DIR a hľadá páry:

      TESTS_DIR/test-XXX/stdout
      TESTS_DIR/test-XXX/workdir/actual-stdout

    a porovná ich obsah. Keď sú rozdielne, vráti zoznam dvojíc
    (test_name, diff_text). Ak je všetko OK, vráti [].
    """
    print(">>> Hľadám rozdiely medzi stdout a actual-stdout v testoch...")
    diffs = []
    if not os.path.isdir(TESTS_DIR):
        print(f"!!! TESTS_DIR neexistuje alebo nie je adresár: {TESTS_DIR}")
        return []

    # Aby to šlo pekne po poradí test-001, test-002, ...
    for entry in sorted(os.scandir(TESTS_DIR), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        test_dir = entry.path
        expected_path = os.path.join(test_dir, "stdout")
        actual_path = os.path.join(test_dir, "workdir", "actual-stdout")
        if not (os.path.exists(expected_path) and os.path.exists(actual_path)):
            continue

        with open(expected_path, "r", encoding="utf-8", errors="ignore") as f:
            expected = f.read()
        with open(actual_path, "r", encoding="utf-8", errors="ignore") as f:
            actual = f.read()

        if expected != actual:
            exp_short = (
                expected[:max_chars] + "...\n[TRUNCATED]"
                if len(expected) > max_chars else expected
            )
            act_short = (
                actual[:max_chars] + "...\n[TRUNCATED]"
                if len(actual) > max_chars else actual
            )

            diff_text = (
                f"Test: {os.path.basename(test_dir)}\n"
                f"OČAKÁVANÝ stdout:\n{exp_short}\n\n"
                f"AKTUÁLNY stdout:\n{act_short}\n"
            )
            diffs.append((os.path.basename(test_dir), diff_text))

    if not diffs:
        print(">>> Žiadne rozdiely stdout vs actual-stdout som nenašiel.")
        return []

    print(f">>> Našiel som rozdiely v stdout/actual-stdout (počet: {len(diffs)}).")
    return diffs


# ==========================
# HLAVNÁ ITERAČNÁ LOGIKA
# ==========================

def main():
    print(">>> main() START")
    print("ROOT_DIR =", ROOT_DIR)
    print("TESTS_DIR =", TESTS_DIR)
    print("MODEL_NAME =", MODEL_NAME)

    feedback_for_programmer = ""
    last_code = ""  # aktuálna verzia main.c, ktorú bude model opravovať

    for iteration in range(1, MAX_ITERATIONS + 1):
        print("\n==============================")
        print(f"ITERÁCIA {iteration}")
        print("==============================\n")

        # ---------- PROGRAMÁTOR AGENT ----------
        if iteration == 1:
            programmer_message = (
                "Tu je zadanie programu v jazyku C (histogram čísel):\n"
                f"{PROBLEM}\n\n"
                "Napíš kompletný, kompilovateľný C program v jednom súbore main.c.\n"
                "- Súbor sa bude kompilovať na binárku ./main pomocou gcc -std=c99.\n"
                "- Testy sa spúšťajú z podpriečinka tests pomocou 'python3 run-tests.py ../main'.\n\n"
                "DÔLEŽITÉ:\n"
                "- Vráť len čistý C kód, bez Markdownu, bez ``` blokov, bez vysvetlení a komentárov navyše.\n"
            )
        else:
            programmer_message = (
                f"{SHORT_SPEC_HINT}\n\n"
                "Tu je aktuálna verzia programu main.c, ktorá má chyby (skrátená, ak je dlhá):\n\n"
                f"{truncate(last_code, 4000)}\n\n"
                "Tu je stručná spätná väzba z kompilácie/testov (skrátená):\n\n"
                f"{truncate(feedback_for_programmer, 2000)}\n\n"
                "Oprav TENTO kód minimálnymi zmenami tak, aby spĺňal zadanie a prešiel testami.\n"
                "Nemeň funkčné časti zbytočne, snaž sa len opravovať chyby.\n"
                "Vráť novú kompletnú verziu súboru main.c (čistý C kód, bez Markdownu a vysvetlení).\n"
            )

        print(">>> Idem volať PROGRAMÁTORA agenta...")
        code_raw = call_agent(
            role="Programátor v jazyku C",
            goal="Napíš alebo oprav C program tak, aby spĺňal zadanie a prešiel kompiláciou a testami.",
            message=programmer_message,
        )
        code = extract_c_code(code_raw)
        last_code = code  # uložíme si aktuálnu verziu pre ďalšiu iteráciu
        save_code_to_root_dir(code)

        # ---------- KOMPILÁCIA ----------
        success_compile, compiler_stderr = compile_c_code()
        if not success_compile:
            print("❌ Kompilácia zlyhala. Chyby kompilátora:")
            print("----------------------------------------")
            print(compiler_stderr)
            print("----------------------------------------")

            feedback_for_programmer = (
                "Tento C program neprešiel kompiláciou.\n\n"
                "Skrátený výpis chýb z gcc (NEUPRAVUJ ho, len podľa neho oprav kód):\n\n"
                f"{truncate(compiler_stderr, 1500)}\n\n"
                "Oprav program tak, aby sa dal skompilovať bez chýb a zároveň zachoval špecifikáciu histogramu.\n"
            )
            continue  # ďalšia iterácia – nový kód

        print("✅ Kompilácia prebehla úspešne.")

        # ---------- PYTHON TESTY ----------
        tests_ok, tests_stdout, tests_stderr = run_python_tests()
        print(">>> Výstup z run-tests.py (stdout):")
        print("----------------------------------------")
        print(tests_stdout)
        print("----------------------------------------")
        if tests_stderr.strip():
            print(">>> STDERR z run-tests.py:")
            print("----------------------------------------")
            print(tests_stderr)
            print("----------------------------------------")

        # Porovnanie stdout vs actual-stdout – zoznam diffov
        diffs = collect_stdout_differences()

        if tests_ok and not diffs:
            print("🎉 VŠETKY TESTY PREŠLI a stdout sa zhoduje s očakávaným.")
            print(f"Finálny binárny súbor: {os.path.join(ROOT_DIR, BINARY_NAME)}")
            break
        else:
            print("⚠️ Niektoré testy NEPREŠLI alebo stdout sa nezhoduje.")

            first_test_name, first_diff = None, ""
            if diffs:
                print(">>> Rozdiely medzi očakávaným a aktuálnym výstupom (všetky):")
                for test_name, diff_text in diffs:
                    print("----------")
                    print(diff_text)

                # Fókus len na prvý neúspešný test
                first_test_name, first_diff = diffs[0]
                print(f">>> Fokujeme sa na prvý neúspešný test: {first_test_name}")

            timeout_hint = ""
            if "[TIMEOUT" in (tests_stderr or ""):
                timeout_hint = (
                    "Poznámka: Program sa počas spúšťania testov neukončil v časovom limite.\n"
                    "Pravdepodobne obsahuje nekonečný cyklus alebo nesprávne čítanie vstupu.\n"
                    "Skontroluj hlavne:\n"
                    "- či čítaš presne n čísel (for (int i = 0; i < n; i++)),\n"
                    "- podmienky cyklov (while/for),\n"
                    "- korektné ukončenie programu po spracovaní vstupu.\n\n"
                )

            target_test_info = ""
            if first_test_name:
                target_test_info = (
                    f"Oprav najprv tento konkrétny test: {first_test_name}.\n"
                    "Keď bude tento test prechádzať, ďalšie iterácie sa môžu sústrediť na ďalšie testy.\n\n"
                    "Rozdiel očakávaného a aktuálneho výstupu pre tento test:\n"
                    f"{truncate(first_diff, 1500)}\n\n"
                )

            feedback_for_programmer = (
                "Program sa skompiloval, ale neprešiel všetkými testami\n"
                "alebo jeho výstup nesedí s očakávaným.\n\n"
                f"{timeout_hint}"
                f"{target_test_info}"
                "Skrátený výstup z run-tests.py (stdout):\n"
                f"{truncate(tests_stdout, 800)}\n\n"
                "Skrátené chybové hlášky z run-tests.py (stderr):\n"
                f"{truncate(tests_stderr, 600)}\n\n"
                "Na základe týchto informácií uprav C program tak, aby tento test prešiel,\n"
                "a zároveň zachoval špecifikáciu programu (histogram s 9 košmi, formát vstupu/výstupu).\n"
            )

    else:
        print("\n❗ Nepodarilo sa dosiahnuť úspešnú kompiláciu + úspešné testy ani po viacerých iteráciách.")


print(">>> idem volať main()")

if __name__ == "__main__":
    main()
