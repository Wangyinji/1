$ErrorActionPreference = "Stop"
$python = Get-ChildItem -LiteralPath "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter python.exe |
  Select-Object -First 1 -ExpandProperty FullName

if (-not $python) {
  throw "Python was not found. Install Python 3.12 before starting Verita."
}

Set-Location $PSScriptRoot
& $python server.py --port 8080
