import sys
import subprocess

if len(sys.argv) < 4:
    print('Usage: run_worker_with_timeout.py SYMBOL SIDE QTY [TIMEOUT_SECONDS]')
    sys.exit(2)

sym, side, qty = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    timeout = int(sys.argv[4]) if len(sys.argv) >= 5 else 10
except ValueError:
    timeout = 10

cmd = [sys.executable, '-m', 'app.services.broker_worker', sym, side, qty]
print('Running:', ' '.join(cmd), 'with timeout', timeout)
try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    print('\n--- EXIT CODE:', res.returncode)
    print('\n--- STDOUT ---')
    print(res.stdout)
    print('\n--- STDERR ---')
    print(res.stderr)
    sys.exit(res.returncode)
except subprocess.TimeoutExpired as exc:
    print('\n--- TIMEOUT after', timeout, 'seconds ---')
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
    print('ERROR running worker:', e)
    sys.exit(1)
