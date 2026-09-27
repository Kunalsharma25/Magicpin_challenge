import sys
import os
sys.path.insert(0, os.path.abspath("."))
import judge_simulator

os.environ["PYTHONIOENCODING"] = "utf-8"

p = judge_simulator.OpenAIProvider('dummy')
j = judge_simulator.JudgeSimulator(p)

print("--- TESTING AUTO REPLY HELL ---")
ar_pass = j.run('auto_reply_hell')

print("\n--- TESTING INTENT TRANSITION ---")
it_pass = j.run('intent_transition')

print("\n--- TESTING HOSTILE ---")
h_pass = j.run('hostile')

print("\n=== SUMMARY ===")
print(f"Auto-reply Hell: {'PASS' if ar_pass else 'FAIL'}")
print(f"Intent Transition: {'PASS' if it_pass else 'FAIL'}")
print(f"Hostile Handling: {'PASS' if h_pass else 'FAIL'}")

if not (ar_pass and it_pass and h_pass):
    sys.exit(1)
