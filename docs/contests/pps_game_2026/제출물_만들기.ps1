# 제출물 ZIP 만들기와 파일명 점검 (PowerShell 5.1 이상)
# 사용법:  powershell -ExecutionPolicy Bypass -File .\제출물_만들기.ps1 -Name 홍길동
# 하는 일: 1) 실행파일 ZIP 만들기  2) ZIP을 다른 폴더에 풀어 index.html이 같은지 확인
#          3) index.html에 외부 주소가 없는지 검사  4) 제출 파일 4종의 이름과 있는지 점검
param([Parameter(Mandatory=$true)][string]$Name)
$ErrorActionPreference = 'Stop'
$work  = 'C:\Users\user\Elyn-Test\docs\contests\pps_game_2026'
$out   = Join-Path $work '제출용'
$title = '미리도착한하루'
New-Item -ItemType Directory -Force $out | Out-Null

$tmp = Join-Path $env:TEMP ('pps_zip_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $tmp | Out-Null
Copy-Item (Join-Path $work 'index.html') $tmp
New-Item -ItemType Directory -Force (Join-Path $tmp 'assets') | Out-Null
Copy-Item (Join-Path $work 'assets\*.jpg') (Join-Path $tmp 'assets')
$readme = "미리도착한하루`r`n1. index.html을 더블클릭합니다. (크롬 또는 엣지)`r`n2. 인터넷 연결과 설치가 필요 없습니다.`r`n3. 마우스, 터치, 키보드(Tab, Enter, 숫자 1 2 3)로 할 수 있습니다. 소리를 켜면 더 좋습니다. 약 2분.`r`n"
[IO.File]::WriteAllText((Join-Path $tmp '실행방법.txt'), $readme, (New-Object Text.UTF8Encoding($true)))

$zipName = "AI게임_실행파일_${title}_${Name}.zip"
$zipPath = Join-Path $out $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $tmp '*') -DestinationPath $zipPath -Force
Remove-Item $tmp -Recurse -Force
Write-Host "만들었다: $zipPath ($([math]::Round((Get-Item $zipPath).Length/1KB,1)) KB)"

# 다른 폴더에 풀어 확인
$chk = Join-Path $env:TEMP ('pps_chk_' + [guid]::NewGuid().ToString('N'))
Expand-Archive -Path $zipPath -DestinationPath $chk -Force
$same = (Get-FileHash (Join-Path $chk 'index.html')).Hash -eq (Get-FileHash (Join-Path $work 'index.html')).Hash
Write-Host ("풀어서 index.html 동일: " + $same)
Write-Host ("ZIP 안 파일: " + ((Get-ChildItem $chk -Recurse | ForEach-Object { $_.Name }) -join ', '))
Remove-Item $chk -Recurse -Force

# 외부 주소 검사 (SVG 네임스페이스는 제외)
$html = Get-Content (Join-Path $work 'index.html') -Raw -Encoding UTF8
$urls = [regex]::Matches($html, 'https?://[^\s"''<>)]+') | ForEach-Object { $_.Value } | Where-Object { $_ -notmatch 'www\.w3\.org' } | Sort-Object -Unique
if ($urls) { Write-Host ("외부 주소 발견(확인 필요): " + ($urls -join ', ')) } else { Write-Host '외부 주소 없음' }

# 제출 파일 4종 점검
$need = @(
  "참가신청서_AI게임_${Name}.pdf",
  "AI게임_시연영상_${title}_${Name}.mp4",
  $zipName,
  "개인정보동의서_${Name}.pdf")
Write-Host "--- 제출 파일 4종 (폴더: $out) ---"
foreach ($f in $need) {
  $p = Join-Path $out $f
  if (Test-Path $p) { Write-Host ("있음  " + $f + "  " + [math]::Round((Get-Item $p).Length/1MB,2) + " MB") }
  else { Write-Host ("없음  " + $f) }
}
Write-Host '이메일 제목: [2026 조달청 공모전] AI게임_'$Name'_'$title -Separator ''
