$ErrorActionPreference = "Stop"

$distDirectory = Join-Path $PSScriptRoot "..\dist"
New-Item -ItemType Directory -Path $distDirectory -Force | Out-Null

# Include the full license files and versions from the exact build environment.
python -m pip install "pip-licenses==5.0.0"
$pythonLicenses = Join-Path $distDirectory "Third-Party-Python-Licenses.txt"
pip-licenses --from=mixed --format=plain-vertical --with-license-file --no-license-path "--output-file=$pythonLicenses"

# LGPLv3 incorporates GPLv3 terms; ship both canonical texts with the installer.
$lgplPath = Join-Path $distDirectory "LGPL-3.0.txt"
$gplPath = Join-Path $distDirectory "GPL-3.0.txt"
Invoke-WebRequest -Uri "https://www.gnu.org/licenses/lgpl-3.0.txt" -OutFile $lgplPath
Invoke-WebRequest -Uri "https://www.gnu.org/licenses/gpl-3.0.txt" -OutFile $gplPath

if (-not (Select-String -Path $lgplPath -Pattern "GNU LESSER GENERAL PUBLIC LICENSE" -Quiet)) {
    throw "Downloaded LGPLv3 text failed validation."
}
if (-not (Select-String -Path $gplPath -Pattern "GNU GENERAL PUBLIC LICENSE" -Quiet)) {
    throw "Downloaded GPLv3 text failed validation."
}

# PyInstaller embeds the Python runtime; preserve the exact runtime license.
$pythonPrefix = (& python -c "import sys; print(sys.base_prefix)").Trim()
$pythonLicensePath = Join-Path $pythonPrefix "LICENSE.txt"
if (-not (Test-Path $pythonLicensePath)) {
    throw "Python runtime LICENSE.txt was not found at $pythonLicensePath"
}
Copy-Item -LiteralPath $pythonLicensePath -Destination (Join-Path $distDirectory "Python-Runtime-LICENSE.txt") -Force
