# Exports every slide of diagrams_en.pptx to diagram_<n>.png (requires PowerPoint).
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = New-Object -ComObject PowerPoint.Application
$p = $app.Presentations.Open((Join-Path $here "diagrams_en.pptx"), $true, $false, $false)
foreach ($i in 1..$p.Slides.Count) { $p.Slides.Item($i).Export((Join-Path $here ("diagram_{0}.png" -f $i)), "PNG", 4000, 2250) }
$p.Close(); $app.Quit()
