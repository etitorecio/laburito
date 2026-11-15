$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "No encuentro Docker. Instalá Docker Desktop para Windows y volvé a ejecutar este archivo." -ForegroundColor Yellow
    Write-Host "https://www.docker.com/products/docker-desktop/"
    exit 1
}

$dockerReady = $false
try {
    docker info *> $null
    $dockerReady = ($LASTEXITCODE -eq 0)
} catch {
    $dockerReady = $false
}
if (-not $dockerReady) {
    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) {
        Write-Host "Iniciando Docker Desktop..." -ForegroundColor Cyan
        Start-Process $desktop
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            Start-Sleep -Seconds 5
            docker info *> $null
            if ($LASTEXITCODE -eq 0) {
                $dockerReady = $true
                break
            }
        }
    }
}
if (-not $dockerReady) {
    Write-Host "Docker Desktop no está listo. Abrilo, esperá a que diga Engine running y ejecutá de nuevo." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

Write-Host "Construyendo e iniciando Laburito. La primera compilación puede tardar." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo iniciar. Revisá el mensaje de Docker y volvé a ejecutar start_windows.bat." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Laburito está iniciando en http://localhost:8080" -ForegroundColor Green
Write-Host "No necesitás claves ni tokens de IA. El primer inicio descarga Qwen 2.5 1.5B (aprox. 1 GB) para escribir guiones localmente."
Write-Host "Para publicar en YouTube: configurá YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET en .env y reiniciá con docker compose up -d."
Write-Host "No borres la carpeta data: conserva la programación, los videos y la autorización."
$lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -match "Wi-Fi|Ethernet" -and $_.IPAddress -notmatch "^(127|169\.254)\." } |
    Select-Object -First 1 -ExpandProperty IPAddress
if ($lan) {
    Write-Host "Desde el celular en la misma Wi-Fi: http://$($lan):8080" -ForegroundColor Cyan
}
Start-Process "http://localhost:8080"
