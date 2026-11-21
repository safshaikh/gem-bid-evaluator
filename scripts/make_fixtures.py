"""Generate synthetic bidder evidence PDFs using reportlab and Pillow for offline testing."""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

FIXTURES_DIR = Path("fixtures")


def generate_pass_pdf(dest: Path) -> None:
    """Generate bidder_pass.pdf with 2 completed orders, OEM auth, and undertaking."""
    c = canvas.Canvas(str(dest), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "Technical Bid Submission - PassBidder Pvt Ltd")
    c.setFont("Helvetica", 11)
    c.drawString(50, 710, "1. Experience Proof:")
    c.drawString(70, 690, "Successfully completed 2 government orders for IT equipment.")
    c.drawString(70, 670, "Contract copy with invoices self-certified by bidder attached herewith.")
    c.drawString(70, 650, "Execution certificate by client with contract value verified.")
    c.drawString(50, 610, "2. Manufacturer Authorization:")
    c.drawString(70, 590, "Authorisation Form / Certificate with OEM details furnished.")
    c.drawString(50, 550, "3. Financial Standing Undertaking:")
    c.drawString(70, 530, "Undertaking to the effect of financial standing and no liquidation.")
    c.drawString(50, 490, "4. Annual Financial Turnover:")
    c.drawString(70, 470, "FY 2023-24: Rs 65,00,000 | FY 2022-23: Rs 70,00,000 | FY 2021-22: Rs 60,00,000")
    c.showPage()
    c.save()


def generate_fail_pdf(dest: Path) -> None:
    """Generate bidder_fail.pdf with only 1 order and missing OEM authorization."""
    c = canvas.Canvas(str(dest), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "Technical Bid Submission - FailBidder Pvt Ltd")
    c.setFont("Helvetica", 11)
    c.drawString(50, 710, "1. Experience Proof:")
    c.drawString(70, 690, "Successfully completed 1 order only for IT equipment.")
    c.drawString(70, 670, "Contract copy with single invoice attached.")
    c.drawString(50, 630, "2. Manufacturer Authorization:")
    c.drawString(70, 610, "Not applicable / Reseller without OEM authorization.")
    c.drawString(50, 570, "3. Financial Standing Undertaking:")
    c.drawString(70, 550, "Undertaking to the effect of financial standing and no liquidation.")
    c.showPage()
    c.save()


def generate_review_pdf(dest: Path) -> None:
    """Generate bidder_review.pdf with mismatched experience quote and only 2 years turnover."""
    c = canvas.Canvas(str(dest), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "Technical Bid Submission - ReviewBidder Pvt Ltd")
    c.setFont("Helvetica", 11)
    c.drawString(50, 710, "1. Experience Proof:")
    c.drawString(70, 690, "Successfully completed two commercial contracts in hardware supply.")
    c.drawString(70, 670, "Contract copy attached.")
    c.drawString(50, 630, "2. Annual Financial Turnover:")
    c.drawString(70, 610, "Annual Turnover FY 2023-24: Rs 60,00,000")
    c.drawString(70, 590, "Annual Turnover FY 2022-23: Rs 55,00,000")
    c.showPage()
    c.save()


def generate_scanned_clean_pdf(dest: Path) -> None:
    """Generate image-only scanned PDF with CA turnover certificate and OEM authorization (zero digital text layer)."""
    img = Image.new("RGB", (1200, 1600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(40, 40), (1160, 1560)], outline=(180, 180, 180), width=3)
    draw.text((80, 100), "CHARTERED ACCOUNTANT STATUTORY TURNOVER CERTIFICATE", fill=(20, 20, 20))
    draw.text((80, 160), "TO WHOMSOEVER IT MAY CONCERN", fill=(40, 40, 40))
    draw.text((80, 240), "This is to certify that M/s ScannedCleanBidder Pvt Ltd has achieved the following", fill=(30, 30, 30))
    draw.text((80, 280), "Annual Financial Turnover for the preceding three financial years:", fill=(30, 30, 30))
    draw.text((120, 360), "1. Financial Year 2023-24: Rs 65,00,000/- (Sixty Five Lakhs Only)", fill=(10, 10, 10))
    draw.text((120, 420), "2. Financial Year 2022-23: Rs 70,00,000/- (Seventy Lakhs Only)", fill=(10, 10, 10))
    draw.text((120, 480), "3. Financial Year 2021-22: Rs 60,00,000/- (Sixty Lakhs Only)", fill=(10, 10, 10))
    draw.text((80, 560), "Average Annual Turnover: Rs 65,00,000/- (Exceeds required threshold)", fill=(20, 20, 20))
    draw.text((80, 700), "MANUFACTURER AUTHORISATION FORM (OEM AUTHORIZATION)", fill=(20, 20, 20))
    draw.text((80, 760), "We hereby confirm that ScannedCleanBidder Pvt Ltd is our certified OEM authorized dealer.", fill=(30, 30, 30))
    draw.text((80, 820), "Authorisation Form / Certificate with OEM details furnished herewith.", fill=(30, 30, 30))
    draw.text((80, 960), "UNDERTAKING: Undertaking to the effect of financial standing and no liquidation.", fill=(30, 30, 30))
    draw.text((80, 1100), "[SEAL & SIGNATURE: STATUTORY AUDITOR & CHARTERED ACCOUNTANT]", fill=(60, 60, 60))

    temp_img = dest.parent / "temp_clean_scan.png"
    img.save(temp_img, format="PNG")

    c = canvas.Canvas(str(dest), pagesize=letter)
    c.drawImage(str(temp_img), 0, 0, width=letter[0], height=letter[1])
    c.showPage()
    c.save()
    if temp_img.is_file():
        temp_img.unlink()


def generate_scanned_blurry_pdf(dest: Path) -> None:
    """Generate deliberately blurry/rotated scanned PDF to test ambiguity and safe degradation."""
    img = Image.new("RGB", (1200, 1600), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(40, 40), (1160, 1560)], outline=(160, 160, 160), width=2)
    draw.text((80, 120), "ANNUAL TURNOVER CERTIFICATE (ILLEGIBLE SCAN)", fill=(80, 80, 80))
    draw.text((80, 220), "Turnover Year 1: Rs ??,00,000 (Blurred and unreadable)", fill=(100, 100, 100))
    draw.text((80, 300), "Turnover Year 2: Rs 15,00,000 (Low turnover / illegible seal)", fill=(100, 100, 100))
    draw.text((80, 420), "Authorisation: Reseller authorization not clearly stamped", fill=(100, 100, 100))

    blurred = img.filter(ImageFilter.GaussianBlur(radius=7))
    rotated = blurred.rotate(15, fillcolor=(255, 255, 255))

    temp_img = dest.parent / "temp_blurry_scan.png"
    rotated.save(temp_img, format="PNG")

    c = canvas.Canvas(str(dest), pagesize=letter)
    c.drawImage(str(temp_img), 0, 0, width=letter[0], height=letter[1])
    c.showPage()
    c.save()
    if temp_img.is_file():
        temp_img.unlink()


def make_all_fixtures() -> None:
    """Create all synthetic bidder PDFs inside fixtures/."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    generate_pass_pdf(FIXTURES_DIR / "bidder_pass.pdf")
    generate_fail_pdf(FIXTURES_DIR / "bidder_fail.pdf")
    generate_review_pdf(FIXTURES_DIR / "bidder_review.pdf")
    generate_scanned_clean_pdf(FIXTURES_DIR / "bidder_scanned_clean.pdf")
    generate_scanned_blurry_pdf(FIXTURES_DIR / "bidder_scanned_blurry.pdf")


if __name__ == "__main__":
    make_all_fixtures()
    print("Generated all fixtures including bidder_scanned_clean.pdf and bidder_scanned_blurry.pdf under fixtures/")
