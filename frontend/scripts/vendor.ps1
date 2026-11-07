# 下载并解包类型检查所需的最小依赖（绕过 npm 在沙箱里不能 spawn 的限制）
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tmp = Join-Path $root '.tarballs'
$nm = Join-Path $root 'node_modules'

$pkgs = @(
  @{ name = 'typescript';          ver = '5.6.3'  },
  @{ name = 'react';               ver = '18.3.1' },
  @{ name = 'react-dom';           ver = '18.3.1' },
  @{ name = '@types/react';        ver = '18.3.11' },
  @{ name = '@types/react-dom';    ver = '18.3.1' },
  @{ name = 'csstype';             ver = '3.1.3' }
)

foreach ($p in $pkgs) {
  $base = ($p.name -split '/')[-1]
  $file = Join-Path $tmp "$base-$($p.ver).tgz"
  if (-not (Test-Path $file)) { Write-Output "missing $file"; continue }
  $dest = Join-Path $nm ($p.name -replace '/', '\')
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  & tar.exe -xzf $file -C $dest --strip-components=1
  if ($LASTEXITCODE -eq 0) { Write-Output "OK $($p.name)@$($p.ver)" } else { Write-Output "FAIL $($p.name)" }
}
