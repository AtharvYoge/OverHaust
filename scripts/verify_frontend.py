#!/usr/bin/env python3
"""Ad-hoc verification for the frontend product milestone (App.tsx).

Checks:
  - TypeScript type-checks cleanly (npx tsc --noEmit)
  - Production build succeeds (npm run build)
  - Build artifact exists (dist/index.html)
  - App.tsx contains all 9 demo steps
  - No fake/token-fabrication language
"""
import subprocess, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
WEB = str(WEB)
APPTSX = os.path.join(WEB, "src/App.tsx")
fails = []

def check(name, cond):
    print(('PASS' if cond else 'FAIL') + f': {name}')
    if not cond: fails.append(name)

# 1. TypeScript type-check
r = subprocess.run(["npx", "tsc", "--noEmit"], cwd=WEB, capture_output=True, text=True)
check('tsc --noEmit clean', r.returncode == 0)

# 2. Production build
r = subprocess.run(["npm", "run", "build"], cwd=WEB, capture_output=True, text=True)
check('npm run build succeeds', r.returncode == 0 and 'built in' in r.stdout)

# 3. Build artifact exists
check('dist/index.html exists', os.path.exists(os.path.join(WEB, "dist/index.html")))

# 4. App.tsx has all demo steps
src = open(APPTSX).read()
for s in ['Are Your AI Tokens', 'Add something for your AI to remember',
          'Reading your conversation', "Your AI doesn't need all of this",
          'What are you working on', 'Ready for your AI', 'Copy for AI',
          'AI memory is saved', 'How Overhaust Works']:
    check(f'contains step text: {s[:30]}', s in src)

# 5. No token fabrication
check('uses estimated label', 'Estimated' in src or 'estimated' in src)
check('does not claim real savings', 'actual savings' not in src.lower())
# 6. Product rule: never show negative reduction
check('has "already compact" branch', 'already compact' in src.lower())
check('guards prep >= orig', 'prep >= orig' in src)

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('ALL AD-HOC FRONTEND CHECKS PASSED')
