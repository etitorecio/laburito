$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "No encuentro Docker. Instalá Docker Desktop para Windows y volvé a ejecutar este archivo." -ForegroundColor Yellow
    Write-Host "https://www.docker.com/products/docker-desktop/"
    exit 1
}

try {
    docker info *> $null
} catch {
    Write-Host "Docker Desktop no está iniciado. Abrilo, esperá a que diga Engine running y ejecutá de nuevo." -ForegroundColor Yellow
    exit 1
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop no está listo. Abrilo, esperá a que diga Engine running y ejecutá de nuevo." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$envText = Get-Content ".env" -Raw
if ($envText -match "APP_TOKEN=CAMBIAR_POR_UN_TOKEN_LARGO_Y_ALEATORIO") {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $token = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    $envText = $envText -replace "APP_TOKEN=.*", "APP_TOKEN=$token"
    Set-Content -Path ".env" -Value $envText -Encoding UTF8
    Write-Host "Se creó un APP_TOKEN aleatorio. Lo podés consultar en el archivo .env." -ForegroundColor Green
}

Write-Host "Construyendo e iniciando Laburito. La primera compilación puede tardar." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo iniciar. Revisá el mensaje de Docker y volvé a ejecutar start_windows.bat." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Laburito está iniciando en http://localhost:8080" -ForegroundColor Green
Write-Host "El APP_TOKEN está guardado en .env; ingresalo en Ajustes > Acceso."
Write-Host "Para YouTube: configurá YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET en .env y reiniciá con docker compose up -d."
Write-Host "No borres la carpeta data: conserva la programación, los videos y la autorización."
$lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -match "Wi-Fi|Ethernet" -and $_.IPAddress -notmatch "^(127|169\.254)\." } |
    Select-Object -First 1 -ExpandProperty IPAddress
if ($lan) {
    Write-Host "Desde el celular en la misma Wi-Fi: http://$($lan):8080" -ForegroundColor Cyan
}
Start-Process "http://localhost:8080"
