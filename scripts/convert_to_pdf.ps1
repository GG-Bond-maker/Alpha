param(
    [Parameter(Mandatory=$true)][string]$src,
    [Parameter(Mandatory=$true)][string]$dst
)
$src = [System.IO.Path]::GetFullPath($src)
$dst = [System.IO.Path]::GetFullPath($dst)

$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($src)
    $wdFormatPDF = 17
    $doc.SaveAs([ref]$dst, [ref]$wdFormatPDF)
    $doc.Close([ref]0)
    Write-Output ("SUCCESS: " + (Test-Path $dst))
} catch {
    Write-Error $_.Exception.Message
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
