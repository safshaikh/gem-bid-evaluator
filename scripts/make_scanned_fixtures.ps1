Add-Type -AssemblyName System.Drawing

$fixturesDir = Join-Path $PSScriptRoot "..\fixtures"
if (-not (Test-Path $fixturesDir)) {
    New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
}

function Save-ImageAsPdf {
    param(
        [string]$PdfPath,
        [System.Drawing.Bitmap]$Bitmap
    )
    $ms = New-Object System.IO.MemoryStream
    $Bitmap.Save($ms, [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $jpegBytes = $ms.ToArray()
    $ms.Dispose()

    $w = $Bitmap.Width
    $h = $Bitmap.Height

    $outStream = New-Object System.IO.MemoryStream
    $writer = New-Object System.IO.BinaryWriter $outStream
    $offsets = New-Object System.Collections.Generic.List[long]
    $offsets.Add(0)

    $header = [System.Text.Encoding]::ASCII.GetBytes("%PDF-1.4`n")
    $writer.Write($header)

    # 1: Catalog
    $offsets.Add($outStream.Position)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("1 0 obj`n<< /Type /Catalog /Pages 2 0 R >>`nendobj`n"))

    # 2: Pages
    $offsets.Add($outStream.Position)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("2 0 obj`n<< /Type /Pages /Kids [3 0 R] /Count 1 >>`nendobj`n"))

    # 3: Page
    $offsets.Add($outStream.Position)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("3 0 obj`n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>`nendobj`n"))

    # 4: Image XObject
    $offsets.Add($outStream.Position)
    $len = $jpegBytes.Length
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("4 0 obj`n<< /Type /XObject /Subtype /Image /Width $w /Height $h /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length $len >>`nstream`n"))
    $writer.Write($jpegBytes)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("`nendstream`nendobj`n"))

    # 5: Contents
    $content = "q 612 0 0 792 0 0 cm /Im1 Do Q`n"
    $cBytes = [System.Text.Encoding]::ASCII.GetBytes($content)
    $cLen = $cBytes.Length
    $offsets.Add($outStream.Position)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("5 0 obj`n<< /Length $cLen >>`nstream`n$content`nendstream`nendobj`n"))

    # XRef
    $xrefPos = $outStream.Position
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("xref`n0 6`n0000000000 65535 f `n"))
    for ($i = 1; $i -le 5; $i++) {
        $line = "{0:D10} 00000 n `n" -f $offsets[$i]
        $writer.Write([System.Text.Encoding]::ASCII.GetBytes($line))
    }
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("trailer`n<< /Size 6 /Root 1 0 R >>`nstartxref`n$xrefPos`n%%EOF`n"))

    [System.IO.File]::WriteAllBytes($PdfPath, $outStream.ToArray())
    $writer.Dispose()
    $outStream.Dispose()
}

# 1. Generate Clean Scanned Certificate
$cleanPath = Join-Path $fixturesDir "bidder_scanned_clean.pdf"
$bmpClean = New-Object System.Drawing.Bitmap 1240, 1754
$gClean = [System.Drawing.Graphics]::FromImage($bmpClean)
$gClean.Clear([System.Drawing.Color]::FromArgb(252, 252, 250))

$penBorder = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(180, 180, 180)), 2
$gClean.DrawRectangle($penBorder, 60, 60, 1120, 1634)

$fontH1 = New-Object System.Drawing.Font ("Arial", [float]20.0, [System.Drawing.FontStyle]::Bold)
$fontH2 = New-Object System.Drawing.Font ("Arial", [float]14.0, [System.Drawing.FontStyle]::Bold)
$fontBody = New-Object System.Drawing.Font ("Arial", [float]13.0, [System.Drawing.FontStyle]::Regular)
$fontSub = New-Object System.Drawing.Font ("Arial", [float]11.0, [System.Drawing.FontStyle]::Italic)

$brushDark = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(20, 20, 20))
$brushMed = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(60, 60, 60))
$brushBlue = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(30, 60, 180))

$gClean.DrawString("OFFICIAL CHARTERED ACCOUNTANT CERTIFICATE", $fontH1, $brushDark, 120.0, 120.0)
$gClean.DrawString("Statutory Turnover & OEM Authorisation Scrutiny Record", $fontSub, $brushMed, 120.0, 170.0)

# Section 1: Turnover
$gClean.DrawString("1. ANNUAL FINANCIAL TURNOVER (AUDITED):", $fontH2, $brushDark, 120.0, 260.0)
$gClean.DrawString("Financial Year 2023-24: INR 65,00,000 (Rupees Sixty Five Lakh)", $fontBody, $brushDark, 160.0, 310.0)
$gClean.DrawString("Financial Year 2022-23: INR 70,00,000 (Rupees Seventy Lakh)", $fontBody, $brushDark, 160.0, 360.0)
$gClean.DrawString("Financial Year 2021-22: INR 60,00,000 (Rupees Sixty Lakh)", $fontBody, $brushDark, 160.0, 410.0)
$gClean.DrawString("Average Annual Turnover: INR 65,00,000 / certified by CA.", $fontBody, $brushDark, 160.0, 460.0)

# Section 2: OEM
$gClean.DrawString("2. MANUFACTURER AUTHORISATION DECLARATION:", $fontH2, $brushDark, 120.0, 560.0)
$gClean.DrawString("OEM Authorisation Certificate Form with OEM details furnished.", $fontBody, $brushDark, 160.0, 610.0)
$gClean.DrawString("Direct Manufacturer Partnership Validated for IT Hardware.", $fontBody, $brushDark, 160.0, 660.0)

# Section 3: Undertaking
$gClean.DrawString("3. UNDERTAKING & FINANCIAL STANDING:", $fontH2, $brushDark, 120.0, 760.0)
$gClean.DrawString("Undertaking to the effect of financial standing and no liquidation.", $fontBody, $brushDark, 160.0, 810.0)

# Auditor Stamp
$penStamp = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(30, 60, 180)), 3
$gClean.DrawRectangle($penStamp, 750, 1350, 350, 230)
$gClean.DrawString("[SEAL & STAMP OF AUDITOR]", $fontH2, $brushBlue, 770.0, 1380.0)
$gClean.DrawString("Signed: R. K. Sharma & Co.", $fontBody, $brushBlue, 770.0, 1430.0)
$gClean.DrawString("CA Reg: #084920 / Peer Reviewed", $fontBody, $brushBlue, 770.0, 1480.0)

Save-ImageAsPdf -PdfPath $cleanPath -Bitmap $bmpClean
$gClean.Dispose()
$bmpClean.Dispose()
Write-Output "Generated clean scanned fixture: $cleanPath"

# 2. Generate Blurry Scanned Certificate
$blurryPath = Join-Path $fixturesDir "bidder_scanned_blurry.pdf"
$bmpBlurry = New-Object System.Drawing.Bitmap 1240, 1754
$gBlurry = [System.Drawing.Graphics]::FromImage($bmpBlurry)
$gBlurry.Clear([System.Drawing.Color]::FromArgb(235, 235, 233))

# Draw faint / skewed unreadable markings
$penFaint = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(210, 210, 210)), 1
$gBlurry.DrawRectangle($penFaint, 80, 80, 1080, 1594)

$fontBlurTitle = New-Object System.Drawing.Font ("Arial", [float]16.0, [System.Drawing.FontStyle]::Italic)
$fontBlurBody = New-Object System.Drawing.Font ("Arial", [float]11.0, [System.Drawing.FontStyle]::Regular)
$brushFaint = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(160, 160, 160))

$gBlurry.TranslateTransform(620.0, 877.0)
$gBlurry.RotateTransform(32.0)
$gBlurry.TranslateTransform(-620.0, -877.0)

$gBlurry.DrawString("LOW RESOLUTION UNREADABLE SCAN CERTIFICATE", $fontBlurTitle, $brushFaint, 140.0, 300.0)
$gBlurry.DrawString("Turnover FY 23-24: Rs ??,00,000 [Illegible smudge]", $fontBlurBody, $brushFaint, 180.0, 420.0)
$gBlurry.DrawString("OEM Authorisation: [Smudged unreadable manufacturer mark]", $fontBlurBody, $brushFaint, 180.0, 520.0)
$gBlurry.DrawString("Auditor Registration: [Blurred illegible digits]", $fontBlurBody, $brushFaint, 180.0, 620.0)

Save-ImageAsPdf -PdfPath $blurryPath -Bitmap $bmpBlurry
$gBlurry.Dispose()
$bmpBlurry.Dispose()
Write-Output "Generated blurry scanned fixture: $blurryPath"
