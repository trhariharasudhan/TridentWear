$names = @("privacy", "terms", "shipping", "returns")
$favicon = '    <link rel="icon" type="image/png" href="/assets/images/Logo.png" />'

foreach ($name in $names) {
    $file = "frontend\pages\legal\$name.html"
    $lines = [System.IO.File]::ReadAllLines((Resolve-Path $file).Path)
    
    # Find stylesheet line and insert favicon before it
    $insertAt = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'rel="stylesheet"' -and $insertAt -eq -1) {
            $insertAt = $i
        }
        if ($lines[$i] -match 'rel="icon"') {
            $insertAt = -2  # Already has it
            break
        }
    }

    if ($insertAt -ge 0) {
        $newLines = $lines[0..($insertAt-1)] + @($favicon) + $lines[$insertAt..($lines.Count-1)]
        [System.IO.File]::WriteAllLines((Resolve-Path $file).Path, $newLines)
        Write-Host "Added favicon to $name"
    } elseif ($insertAt -eq -2) {
        Write-Host "Favicon already in $name"
    }

    $verify = Get-Content $file
    $fv = ($verify | Select-String 'rel="icon"').Count
    $bttv = ($verify | Select-String 'back-to-top').Count
    Write-Host "  -> $name : lines=$($verify.Count)  favicon=$fv  back-to-top=$bttv"
}
