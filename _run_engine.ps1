$env:PYTHONIOENCODING = 'utf-8'
$content = @'
"""Run derive_data_conditions for TEST60 role 1803."""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from meta.server import create_app
app = create_app()
with app.app_context():
    from meta.services.dimension_scope_engine import DimensionScopeEngine
    from meta.services.query_service import _get_data_source
    ds = _get_data_source()
    eng = DimensionScopeEngine(ds)

    print("--- TEST60 role 1803 ---", flush=True)
    print("expand:", eng.expand_dimension_values(1803), flush=True)
    print("conditions:", eng.derive_data_conditions(1803), flush=True)
    print()
    print("--- admin role 1 ---", flush=True)
    print("expand:", eng.expand_dimension_values(1), flush=True)
    print("conditions:", eng.derive_data_conditions(1), flush=True)
'@
[System.IO.File]::WriteAllText("verify_engine.py", $content, [System.Text.Encoding]::UTF8)
python verify_engine.py 1> out.txt 2> err.txt
Write-Host "---OUT---"
Get-Content out.txt
Write-Host "---ERR---"
Get-Content err.txt
