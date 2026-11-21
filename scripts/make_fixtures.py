"""Generate synthetic bidder evidence PDFs using reportlab for offline testing."""

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
    """Generate a clean image-only scanned PDF with turnover and OEM authorisation."""
    img = Image.new("RGB", (1240, 1754), color=(252, 252, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(60, 60), (1180, 1694)], outline=(180, 180, 180), width=2)
    draw.text((120, 120), "OFFICIAL CHARTERED ACCOUNTANT CERTIFICATE", fill=(20, 20, 20))
    draw.text((120, 160), "Statutory Turnover & OEM Authorisation Scrutiny Record", fill=(60, 60, 60))

    # 1. Turnover details
    draw.text((120, 260), "1. ANNUAL FINANCIAL TURNOVER (AUDITED):", fill=(0, 0, 0))
    draw.text((160, 310), "Financial Year 2023-24: INR 65,00,000 (Rupees Sixty Five Lakh)", fill=(30, 30, 30))
    draw.text((160, 360), "Financial Year 2022-23: INR 70,00,000 (Rupees Seventy Lakh)", fill=(30, 30, 30))
    draw.text((160, 410), "Financial Year 2021-22: INR 60,00,000 (Rupees Sixty Lakh)", fill=(30, 30, 30))
    draw.text((160, 460), "Average Annual Turnover: INR 65,00,000 / certified by CA.", fill=(30, 30, 30))

    # 2. OEM Authorization details
    draw.text((120, 560), "2. MANUFACTURER AUTHORISATION DECLARATION:", fill=(0, 0, 0))
    draw.text((160, 610), "OEM Authorisation Certificate Form with OEM details furnished.", fill=(30, 30, 30))
    draw.text((160, 660), "Direct Manufacturer Partnership Validated for IT Hardware.", fill=(30, 30, 30))

    # 3. Undertaking details
    draw.text((120, 760), "3. UNDERTAKING & FINANCIAL STANDING:", fill=(0, 0, 0))
    draw.text((160, 810), "Undertaking to the effect of financial standing and no liquidation.", fill=(30, 30, 30))

    # Simulated signature / stamp
    draw.rectangle([(750, 1350), (1100, 1580)], outline=(30, 60, 180), width=3)
    draw.text((770, 1380), "[SEAL & STAMP OF AUDITOR]", fill=(30, 60, 180))
    draw.text((770, 1420), "Signed: R. K. Sharma & Co.", fill=(30, 60, 180))
    draw.text((770, 1460), "CA Reg: #084920 / Peer Reviewed", fill=(30, 60, 180))

    img.save(str(dest), "PDF", resolution=150.0)


def generate_scanned_blurry_pdf(dest: Path) -> None:
    """Generate a deliberately degraded/blurry and rotated scan PDF."""
    img = Image.new("RGB", (1240, 1754), color=(240, 240, 238))
    draw = ImageDraw.Draw(img)

    draw.text((120, 120), "UNVERIFIABLE LOW RESOLUTION CERTIFICATE", fill=(100, 100, 100))
    draw.text((160, 260), "Turnover FY 23-24: Rs ?0,00,000", fill=(120, 120, 120))
    draw.text((160, 320), "OEM Authorization: [Illegible smear / unreadable stamp]", fill=(120, 120, 120))

    degraded = img.filter(ImageFilter.GaussianBlur(radius=9)).rotate(35, expand=False, fillcolor=(240, 240, 240))
    degraded.save(str(dest), "PDF", resolution=100.0)


def make_all_fixtures() -> None:
    """Create all synthetic bidder PDFs inside fixtures/."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if HAS_REPORTLAB:
        generate_pass_pdf(FIXTURES_DIR / "bidder_pass.pdf")
        generate_fail_pdf(FIXTURES_DIR / "bidder_fail.pdf")
        generate_review_pdf(FIXTURES_DIR / "bidder_review.pdf")
    if HAS_PIL:
        generate_scanned_clean_pdf(FIXTURES_DIR / "bidder_scanned_clean.pdf")
        generate_scanned_blurry_pdf(FIXTURES_DIR / "bidder_scanned_blurry.pdf")


if __name__ == "__main__":
    make_all_fixtures()
    print("Fixture status in fixtures/:")
    for f in FIXTURES_DIR.glob("*.pdf"):
        print(f" - {f.name} ({f.stat().st_size} bytes)")
