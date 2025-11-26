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
TESTS_DIR = os.path.join(ROOT_DIR, "")

SOURCE_NAME = "main.c"   # názov C súboru
BINARY_NAME = "main"     # názov binárky (./main)
RUN_TESTS_SCRIPT = "run-tests.py"

# maximálny počet iterácií (generovanie + opravy)
MAX_ITERATIONS = 10

# Názov modelu, ktorý beží vo vLLM serveri
MODEL_NAME = "Qwen/Qwen2.5-Coder-3B-Instruct"

# Zadanie, ktoré má agent implementovať
PROBLEM = """Problem"""

# ==========================
# PRIPOJENIE NA vLLM (OpenAI API kompatibilný server)
# ==========================

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="token-abc123",
)


def call_agent(role: str, goal: str, message: str) -> str:
    """
    Zavolá jedného agenta s danou rolou a cieľom cez vLLM server.
    """
    print(f">>> Volám agenta: {role}")
    system_prompt = f"Si agent s rolou: {role}. Tvoj cieľ: {goal}."
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
    )
    return completion.choices[0].message.content


# ==========================
# POMOCNÉ FUNKCIE PRE KÓD
# ==========================

def extract_c_code(response: str) -> str:
    """
    Ak LLM vráti kód v ```c ... ``` bloku, vytiahne len obsah.
    Inak vráti celý text ako kód.
    """
    fence_match = re.search(r"```(?:c|C|cpp|C\\+\\+)?\\s*(.*?)```", response, re.DOTALL)
    if fence_match:
        code = fence_match.group(1).strip()
        print(">>> Z odpovede som vytiahol kód z ``` blokov.")
        return code
    print(">>> Celá odpoveď sa berie ako kód (žiadne ``` bloky).")
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
      - success (bool) – či run-tests skončil s returncode 0
      - stdout (str) – výpis testov
      - stderr (str) – prípadné chyby z run-tests
    """
    print(">>> Spúšťam python testy (run-tests.py)...")
    proc = subprocess.run(
        ["python3", RUN_TESTS_SCRIPT, f"../{BINARY_NAME}"],
        cwd=TESTS_DIR,
        capture_output=True,
        text=True,
    )
    success = proc.returncode == 0
    return success, proc.stdout, proc.stderr


def collect_stdout_differences(max_chars: int = 400) -> str:
    """
    Prejde všetky podpriečinky v TESTS_DIR a hľadá páry:

      TESTS_DIR/test-XXX/stdout
      TESTS_DIR/test-XXX/workdir/actual-stdout

    a porovná ich obsah. Keď sú rozdielne, pridá ich do reportu.
    """
    print(">>> Hľadám rozdiely medzi stdout a actual-stdout v testoch...")
    diffs = []
    if not os.path.isdir(TESTS_DIR):
        print(f"!!! TESTS_DIR neexistuje alebo nie je adresár: {TESTS_DIR}")
        return ""

    for entry in os.scandir(TESTS_DIR):
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
            exp_short = (expected[:max_chars] + "...\n[TRUNCATED]") if len(expected) > max_chars else expected
            act_short = (actual[:max_chars] + "...\n[TRUNCATED]") if len(actual) > max_chars else actual

            diffs.append(
                f"Test: {os.path.basename(test_dir)}\n"
                f"OČAKÁVANÝ stdout:\n{exp_short}\n\n"
                f"AKTUÁLNY stdout:\n{act_short}\n"
            )

    if not diffs:
        print(">>> Žiadne rozdiely stdout vs actual-stdout som nenašiel.")
        return ""
    print(">>> Našiel som rozdiely v stdout/actual-stdout.")
    return "\n\n".join(diffs)


# ==========================
# HLAVNÁ ITERAČNÁ LOGIKA
# ==========================

def main():
    print(">>> main() START")
    print("ROOT_DIR =", ROOT_DIR)
    print("TESTS_DIR =", TESTS_DIR)
    print("MODEL_NAME =", MODEL_NAME)

    feedback_for_programmer = ""

    for iteration in range(1, MAX_ITERATIONS + 1):
        print("\n==============================")
        print(f"ITERÁCIA {iteration}")
        print("==============================\n")

        # ---------- PROGRAMÁTOR AGENT ----------
        if iteration == 1:
            programmer_message = (
                "Tu je zadanie programu v jazyku C:\n"
                f"{PROBLEM}\n\n"
                "Napíš kompletný, kompilovateľný C program. "
                "Kód bude uložený v súbore main.c v ROOT_DIR a kompilovaný na binárku ./main. "
                "Testy sa spúšťajú v podpriečinku s run-tests.py pomocou 'python3 run-tests.py ../main'. "
                "Vráť len C kód, bez vysvetlení."
            )
        else:
            programmer_message = (
                "Tu je pôvodné zadanie programu v jazyku C:\n"
                f"{PROBLEM}\n\n"
                "Predchádzajúca verzia kódu neprešla kompiláciou alebo testami.\n"
                "Tu je spätná väzba (chyby kompilácie a/nebo rozdiely v testoch):\n"
                f"{feedback_for_programmer}\n\n"
                "Na základe toho oprav program a vráť NOVÚ kompletnú verziu súboru main.c. "
                "Vráť len C kód, bez vysvetlení."
            )

        print(">>> Idem volať PROGRAMÁTORA agenta...")
        code_raw = call_agent(
            role="Programátor v jazyku C",
            goal="Napíš alebo oprav C program tak, aby spĺňal zadanie a prešiel kompiláciou a testami.",
            message=programmer_message,
        )
        code = extract_c_code(code_raw)
        save_code_to_root_dir(code)

        # ---------- KOMPILÁCIA ----------
        success_compile, compiler_stderr = compile_c_code()
        if not success_compile:
            print("❌ Kompilácia zlyhala. Chyby kompilátora:")
            print("----------------------------------------")
            print(compiler_stderr)
            print("----------------------------------------")

            tester_message = (
                "Toto je C kód z main.c, ktorý neprešiel kompiláciou:\n\n"
                f"{code}\n\n"
                "A toto je výpis chýb z gcc:\n\n"
                f"{compiler_stderr}\n\n"
                "1) Zrekapituluj hlavné chyby.\n"
                "2) Navrhni konkrétne úpravy kódu (popíš, čo zmeniť).\n"
                "3) Priprav stručné inštrukcie pre programátora, aby to v ďalšej iterácii opravil."
            )
            tester_feedback = call_agent(
                role="Tester / C expert",
                goal="Analyzuj chyby kompilácie a vysvetli, čo treba v kóde opraviť.",
                message=tester_message,
            )

            feedback_for_programmer = (
                "CHYBY KOMPILÁTORA gcc:\n"
                f"{compiler_stderr}\n\n"
                "ANALÝZA OD TESTERA:\n"
                f"{tester_feedback}\n"
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

        # Porovnanie stdout vs actual-stdout
        diff_text = collect_stdout_differences()

        if tests_ok and not diff_text:
            print("🎉 VŠETKY TESTY PREŠLI a stdout sa zhoduje s očakávaným.")
            print(f"Finálny binárny súbor: {os.path.join(ROOT_DIR, BINARY_NAME)}")
            break
        else:
            print("⚠️ Niektoré testy NEPREŠLI alebo stdout sa nezhoduje.")
            if diff_text:
                print(">>> Rozdiely medzi očakávaným a aktuálnym výstupom:")
                print(diff_text)

            # ---------- TESTOVACÍ AGENT ----------
            test_agent_message = (
                "Máme C program, ktorý sa síce skompiloval, ale neprešiel všetkými testami.\n\n"
                "Výstup z run-tests.py (stdout):\n"
                f"{tests_stdout}\n\n"
                "Prípadné chybové hlášky z run-tests.py (stderr):\n"
                f"{tests_stderr}\n\n"
                "Rozdiely medzi očakávaným a aktuálnym stdout v jednotlivých testoch:\n"
                f"{diff_text if diff_text else '[Žiadne konkrétne diffy neboli nájdené.]'}\n\n"
                "1) Vysvetli, v čom program nesplnil očakávania.\n"
                "2) Navrhni, čo konkrétne v kóde treba zmeniť (logika, parsovanie argumentov, formát výstupu atď.).\n"
                "3) Priprav inštrukcie pre programátora, aby vedel program opraviť tak, aby testy prešli."
            )

            test_agent_feedback = call_agent(
                role="Testovací agent",
                goal="Analyzuj výsledky testov a navrhni, ako upraviť program, aby testy prešli.",
                message=test_agent_message,
            )

            feedback_for_programmer = (
                "VÝSLEDKY TESTOV (run-tests.py stdout):\n"
                f"{tests_stdout}\n\n"
                "CHYBY TESTOV (stderr):\n"
                f"{tests_stderr}\n\n"
                "ROZDIELY stdout vs actual-stdout:\n"
                f"{diff_text}\n\n"
                "ANALÝZA OD TESTOVACIEHO AGENTA:\n"
                f"{test_agent_feedback}\n"
            )

    else:
        print("\n❗ Nepodarilo sa dosiahnuť úspešnú kompiláciu + úspešné testy ani po viacerých iteráciách.")


print(">>> idem volať main()")

if __name__ == "__main__":
    main()
