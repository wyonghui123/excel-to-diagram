import subprocess
import sys
import os

os.chdir(r'd:\filework\excel-to-diagram')
env = os.environ.copy()
env['CI'] = '1'
env['PYTHONIOENCODING'] = 'utf-8'
r = subprocess.run(
    ['cmd', '/c', 'npx', 'vitest', 'run',
     'src/composables/useMermaid/syntax/_shared/__tests__/arrowHelper.spec.js',
     'src/composables/useMermaid/tooltip/__tests__/useTooltip.spec.js',
     '--reporter=verbose', '--no-color'],
    capture_output=True
)
out = r.stdout.decode('utf-8', errors='replace')
err = r.stderr.decode('utf-8', errors='replace')
print('=== STDOUT ===')
print(out)
print('=== STDERR ===')
print(err)
print('RC:', r.returncode)
# Save to file with UTF-8 BOM
with open('vitest_unit.log', 'wb') as f:
    f.write(b'=== STDOUT ===\n')
    f.write(out.encode('utf-8'))
    f.write(b'\n=== STDERR ===\n')
    f.write(err.encode('utf-8'))
    f.write(f'\nRC: {r.returncode}\n'.encode('utf-8'))
print('saved to vitest_unit.log')
