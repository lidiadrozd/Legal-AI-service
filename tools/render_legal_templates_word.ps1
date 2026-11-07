param([string]$PackRoot)
$ErrorActionPreference = 'Stop'
$resolvedRoot = (Resolve-Path -LiteralPath $PackRoot).Path
$qaRoot = Join-Path $resolvedRoot 'qa'
New-Item -ItemType Directory -Path $qaRoot -Force | Out-Null
$word = $null
$results = @()
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    Write-Output ('Renderer: ' + $word.Name + ' ' + $word.Version)
    $sentinel = $word.Documents.Add()
    foreach ($inputFile in (Get-ChildItem -LiteralPath (Join-Path $resolvedRoot 'docx') -Filter '*.docx' | Sort-Object Name)) {
        $document = $null
        try {
            $pdfPath = Join-Path $qaRoot ($inputFile.BaseName + '.pdf')
            $document = $word.Documents.Open($inputFile.FullName, $false, $true, $false)
            $document.Repaginate()
            $pageCount = $document.ComputeStatistics(2)
            $document.ExportAsFixedFormat($pdfPath, 17)
            $results += [pscustomobject]@{ name=$inputFile.Name; pages=$pageCount; status='rendered_with_word'; pdf=$pdfPath }
            Write-Output ($inputFile.Name + ' pages=' + $pageCount)
        } finally {
            if ($null -ne $document) {
                $document.Close(0)
            }
        }
    }
} finally {
    if ($null -ne $word) {
        try { $saveOption = 0; $word.Quit([ref]$saveOption) } catch { Write-Output ('Renderer cleanup: ' + $_.Exception.Message) }
    }
}
$results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $qaRoot 'word_render_manifest.json') -Encoding utf8
