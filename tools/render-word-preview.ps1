param([Parameter(Mandatory=$true)][string[]]$Paths)
$ErrorActionPreference = 'Stop'
$previewRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts/layout-qa'
New-Item -ItemType Directory -Path $previewRoot -Force | Out-Null
foreach ($sourcePath in $Paths) {
    $exported = $false
    # Some Word builds terminate the automation server when its final
    # document closes. Give each input its own hidden automation instance.
    $wordPreview = New-Object -ComObject Word.Application
    $wordPreview.Visible = $false
    $wordPreview.DisplayAlerts = 0
    $wordPreview.AutomationSecurity = 3
    try {
        $resolvedSource = (Resolve-Path -LiteralPath $sourcePath).Path
        $pdfTarget = Join-Path $previewRoot ([IO.Path]::GetFileNameWithoutExtension($resolvedSource) + '.pdf')
        $previewDocument = $wordPreview.Documents.Open($resolvedSource, $false, $true, $false)
        try {
            $previewDocument.ExportAsFixedFormat($pdfTarget, 17)
            $exported = $true
            Write-Output $pdfTarget
        } finally {
            $previewDocument.Close(0)
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($previewDocument)
        }
    } finally {
      try { $wordPreview.Quit() } catch {
        # Some Word builds stop their hidden automation server when its last
        # read-only document closes. The exported PDF is already complete.
        if (-not $exported) { throw }
      }
      [void][Runtime.InteropServices.Marshal]::ReleaseComObject($wordPreview)
    }
}
