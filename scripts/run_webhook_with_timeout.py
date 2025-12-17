import sys
import subprocess

cmd = [sys.executable, 'scripts/run_webhook_tsla_runner.py']
print('Running:', ' '.join(cmd))
try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    print('\n--- EXIT CODE:', res.returncode)
    print('\n--- STDOUT ---')
    print(res.stdout)
    print('\n--- STDERR ---')
    print(res.stderr)
    sys.exit(res.returncode)
except subprocess.TimeoutExpired as exc:
    print('\n--- TIMEOUT after 600 seconds ---')
    print('\n--- PARTIAL STDOUT ---')
    if exc.stdout:
        print(exc.stdout)
    else:
        print('(none)')
    print('\n--- PARTIAL STDERR ---')
    if exc.stderr:
        print(exc.stderr)
    else:
        print('(none)')
    sys.exit(124)
except Exception as e:
    print('ERROR running webhook:', e)
    sys.exit(1)
