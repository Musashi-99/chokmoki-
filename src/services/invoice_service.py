"""On-demand, branded GST document PDFs for the admin panel.

Three document types over one layout engine:
- tax_invoice: the GST tax invoice — taxable value back-calculated from the
  GST-inclusive selling price, split CGST+SGST (customer in the seller's
  state) or IGST (any other state).
- receipt: a payment receipt — same items, plus a payment block (method,
  Razorpay payment id, amount received) instead of the tax declaration.
- bill_of_supply: same document with no tax columns/split — the format used
  when no GST is being charged on the document.

Generated lazily per request, never persisted as a file: the PDF is a pure
function of the order document + config, so regeneration is always
consistent — except the invoice NUMBER, which is assigned exactly once via
an atomic Mongo counter the first time any document is generated for an
order, then stored on the order and reused forever (GST invoice numbers
must be unique and sequential and must never change once issued).

reportlab is synchronous/CPU-bound — callers must run build_pdf via
asyncio.to_thread (the admin route does) so generation never blocks the
event loop.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ReturnDocument
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from src.config import settings
from src.database.connection import db

COUNTERS_COLLECTION = "counters"
ORDERS_COLLECTION = "orders"

DOC_TITLES = {
    "tax_invoice": "TAX INVOICE",
    "receipt": "PAYMENT RECEIPT",
    "bill_of_supply": "BILL OF SUPPLY",
}

_ONES = (
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digits(n: int) -> str:
    if n < 100:
        return _two_digits(n)
    rest = _two_digits(n % 100)
    return (_ONES[n // 100] + " Hundred" + (" " + rest if rest else "")).strip()


def amount_in_words_inr(amount: float) -> str:
    """Indian-numbering words for an INR amount (crore/lakh/thousand)."""
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if rupees == 0:
        words = "Zero"
    else:
        parts: List[str] = []
        crore, rupees = divmod(rupees, 10_000_000)
        lakh, rupees = divmod(rupees, 100_000)
        thousand, hundreds = divmod(rupees, 1000)
        if crore:
            parts.append(_two_digits(crore) + " Crore")
        if lakh:
            parts.append(_two_digits(lakh) + " Lakh")
        if thousand:
            parts.append(_two_digits(thousand) + " Thousand")
        if hundreds:
            parts.append(_three_digits(hundreds))
        words = " ".join(parts)
    result = f"{words} Rupees"
    if paise:
        result += f" and {_two_digits(paise)} Paise"
    return result + " Only"


class InvoiceService:
    async def _db(self):
        return await db.get_database()

    async def get_or_assign_invoice_number(self, order_id: str) -> Tuple[str, datetime]:
        """Assign the order's permanent invoice number exactly once.

        The atomic counter ($inc on a single counters doc) guarantees
        uniqueness + sequence; the conditional order update ($exists: False
        filter) guarantees a concurrent second request can't assign a second
        number — the loser's counter increment is simply an unused gap in
        the sequence, which GST rules tolerate far better than a duplicate
        or a changed number.
        """
        database = await self._db()
        orders = database[ORDERS_COLLECTION]

        existing = await orders.find_one(
            {"order_id": order_id}, {"invoice_number": 1, "invoice_date": 1}
        )
        if existing is None:
            raise ValueError("Order not found")
        if existing.get("invoice_number"):
            return existing["invoice_number"], existing["invoice_date"]

        year = datetime.utcnow().year
        counter = await database[COUNTERS_COLLECTION].find_one_and_update(
            {"_id": f"invoice_number_{year}"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        invoice_number = f"{settings.invoice_number_prefix}-{year}-{counter['seq']:06d}"
        invoice_date = datetime.utcnow()

        claimed = await orders.find_one_and_update(
            {"order_id": order_id, "invoice_number": {"$exists": False}},
            {"$set": {"invoice_number": invoice_number, "invoice_date": invoice_date}},
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            # Lost the race — another request assigned one a moment ago.
            current = await orders.find_one(
                {"order_id": order_id}, {"invoice_number": 1, "invoice_date": 1}
            )
            return current["invoice_number"], current["invoice_date"]
        return invoice_number, invoice_date

    # ---- GST math -------------------------------------------------------

    def _is_intra_state(self, order_doc: Dict[str, Any]) -> bool:
        customer_state = (
            (order_doc.get("shipping_address") or {}).get("state") or ""
        ).strip().lower()
        seller_state = settings.invoice_seller_state.strip().lower()
        return customer_state == seller_state

    def _tax_lines(self, order_doc: Dict[str, Any], doc_type: str) -> List[Dict[str, Any]]:
        """Per-item rows with the GST-inclusive price decomposed into
        taxable value + tax amounts. bill_of_supply keeps the full price as
        the line value with no tax split (that's what the format means).
        """
        rate = settings.gst_total_percent / 100.0 if settings.gst_enabled else 0.0
        split_tax = doc_type != "bill_of_supply" and rate > 0
        intra = self._is_intra_state(order_doc)

        rows = []
        for item in order_doc.get("items", []):
            qty = int(item.get("quantity", 1))
            unit_price = float(item.get("unit_price", 0))
            line_total = round(unit_price * qty, 2)
            if split_tax:
                taxable = round(line_total / (1 + rate), 2)
                tax_amount = round(line_total - taxable, 2)
            else:
                taxable = line_total
                tax_amount = 0.0
            half = round(tax_amount / 2, 2)
            rows.append({
                "name": item.get("product_name", "Item"),
                "sku": item.get("product_id", ""),
                "hsn": settings.gst_hsn_code if split_tax else "",
                "qty": qty,
                "unit_price": unit_price,
                "taxable": taxable,
                "cgst": half if (split_tax and intra) else 0.0,
                "sgst": half if (split_tax and intra) else 0.0,
                "igst": tax_amount if (split_tax and not intra) else 0.0,
                "total": line_total,
            })
        return rows

    # ---- PDF layout ------------------------------------------------------

    def build_pdf(
        self,
        order_doc: Dict[str, Any],
        *,
        doc_type: str,
        invoice_number: str,
        invoice_date: datetime,
    ) -> bytes:
        """Synchronous, CPU-bound — run via asyncio.to_thread."""
        import io

        if doc_type not in DOC_TITLES:
            raise ValueError(f"Unknown document type: {doc_type}")

        buffer = io.BytesIO()
        page_w, page_h = A4
        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        margin = 15 * mm
        y = page_h - margin

        burgundy = colors.HexColor("#6b1f2a")
        ink = colors.HexColor("#1a1a1a")
        muted = colors.HexColor("#666666")
        hairline = colors.HexColor("#cccccc")

        # -- Brand header: logo left, document title right
        logo_path = settings.invoice_logo_path
        logo_h = 22 * mm
        if os.path.exists(logo_path):
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            logo_w = logo_h * iw / ih
            c.drawImage(img, margin, y - logo_h, width=logo_w, height=logo_h, mask="auto")
        else:
            c.setFont("Helvetica-Bold", 20)
            c.setFillColor(ink)
            c.drawString(margin, y - 10 * mm, settings.invoice_brand_name)

        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(burgundy)
        c.drawRightString(page_w - margin, y - 8 * mm, DOC_TITLES[doc_type])
        c.setFont("Helvetica", 8)
        c.setFillColor(muted)
        c.drawRightString(page_w - margin, y - 13 * mm, settings.invoice_brand_tagline.upper())
        y -= logo_h + 6 * mm

        c.setStrokeColor(hairline)
        c.setLineWidth(0.6)
        c.line(margin, y, page_w - margin, y)
        y -= 6 * mm

        # -- Three columns: Ship To | Sold By | Document details
        addr = order_doc.get("shipping_address") or {}
        col_w = (page_w - 2 * margin) / 3

        def block(x: float, top: float, title: str, lines: List[str]) -> float:
            c.setFont("Helvetica-Bold", 8.5)
            c.setFillColor(ink)
            c.drawString(x, top, title)
            yy = top - 4.5 * mm
            c.setFont("Helvetica", 8)
            c.setFillColor(muted)
            for line in lines:
                if line:
                    c.drawString(x, yy, line[:48])
                    yy -= 3.8 * mm
            return yy

        ship_lines = [
            addr.get("full_name", ""),
            addr.get("address_line1", ""),
            addr.get("address_line2", ""),
            f"{addr.get('city', '')} {addr.get('postal_code', '')}".strip(),
            f"{addr.get('state', '')}, {addr.get('country', 'India')}",
            f"Ph: {addr.get('phone', '')}" if addr.get("phone") else "",
        ]
        seller_lines = [
            settings.invoice_seller_name,
            settings.invoice_seller_address1,
            settings.invoice_seller_address2,
            f"{settings.invoice_seller_city} {settings.invoice_seller_pincode}",
            f"{settings.invoice_seller_state}, India (State Code: {settings.invoice_seller_state_code})",
            f"GSTIN: {settings.invoice_seller_gstin}",
            f"Ph: {settings.invoice_seller_phone}",
            f"Email: {settings.invoice_seller_email}",
        ]
        created = order_doc.get("created_at")
        order_date_str = created.strftime("%d/%m/%Y") if isinstance(created, datetime) else ""
        detail_lines = [
            f"No.: {invoice_number}",
            f"Date: {invoice_date.strftime('%d/%m/%Y')}",
            f"Order: {order_doc.get('order_id', '')[:23]}",
            f"Order Date: {order_date_str}",
            f"Payment: {(order_doc.get('payment_method') or '').upper()}",
            f"AWB: {order_doc.get('awb_code')}" if order_doc.get("awb_code") else "",
            f"Place of Supply: {addr.get('state', '')}",
        ]
        bottoms = [
            block(margin, y, "SHIP TO / BILL TO:", ship_lines),
            block(margin + col_w, y, "SOLD BY:", seller_lines),
            block(margin + 2 * col_w, y, "DOCUMENT DETAILS:", detail_lines),
        ]
        y = min(bottoms) - 6 * mm

        # -- Items table
        rows = self._tax_lines(order_doc, doc_type)
        intra = self._is_intra_state(order_doc)
        show_tax = doc_type != "bill_of_supply" and settings.gst_enabled
        if show_tax and intra:
            headers = ["S.No", "Product", "HSN", "Qty", "Unit Price", "Taxable Value",
                       f"CGST ({settings.gst_cgst_percent}%)", f"SGST ({settings.gst_sgst_percent}%)", "Total (Incl. GST)"]
            widths = [0.05, 0.29, 0.07, 0.05, 0.11, 0.13, 0.10, 0.10, 0.10]
        elif show_tax:
            headers = ["S.No", "Product", "HSN", "Qty", "Unit Price", "Taxable Value",
                       f"IGST ({self._fmt_rate(settings.gst_total_percent)}%)", "Total (Incl. GST)"]
            widths = [0.05, 0.34, 0.08, 0.05, 0.12, 0.14, 0.10, 0.12]
        else:
            headers = ["S.No", "Product", "Qty", "Unit Price", "Total"]
            widths = [0.06, 0.52, 0.08, 0.16, 0.18]
        widths = [w * (page_w - 2 * margin) for w in widths]

        def table_row(values: List[str], yy: float, *, bold: bool = False) -> float:
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 7.5)
            c.setFillColor(ink if bold else muted)
            x = margin
            for value, w in zip(values, widths):
                c.drawString(x + 1.5 * mm, yy, str(value)[:40])
                x += w
            return yy - 6 * mm

        c.setFillColor(colors.HexColor("#f6f1ee"))
        c.rect(margin, y - 2 * mm, page_w - 2 * margin, 7 * mm, fill=1, stroke=0)
        y = table_row(headers, y, bold=True)
        c.setStrokeColor(hairline)
        c.line(margin, y + 4 * mm, page_w - margin, y + 4 * mm)

        for i, r in enumerate(rows, start=1):
            if show_tax and intra:
                values = [i, r["name"], r["hsn"], r["qty"], f"{r['unit_price']:.2f}",
                          f"{r['taxable']:.2f}", f"{r['cgst']:.2f}", f"{r['sgst']:.2f}", f"{r['total']:.2f}"]
            elif show_tax:
                values = [i, r["name"], r["hsn"], r["qty"], f"{r['unit_price']:.2f}",
                          f"{r['taxable']:.2f}", f"{r['igst']:.2f}", f"{r['total']:.2f}"]
            else:
                values = [i, r["name"], r["qty"], f"{r['unit_price']:.2f}", f"{r['total']:.2f}"]
            y = table_row(values, y)
        c.line(margin, y + 4 * mm, page_w - margin, y + 4 * mm)
        y -= 2 * mm

        # -- Totals block (right-aligned)
        taxable_total = round(sum(r["taxable"] for r in rows), 2)
        cgst_total = round(sum(r["cgst"] for r in rows), 2)
        sgst_total = round(sum(r["sgst"] for r in rows), 2)
        igst_total = round(sum(r["igst"] for r in rows), 2)
        shipping = float(order_doc.get("shipping") or 0)
        discount = float(order_doc.get("discount") or 0)
        grand_total = float(order_doc.get("total_amount") or 0)

        def total_line(label: str, value: str, yy: float, *, bold: bool = False) -> float:
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 8.5 if bold else 8)
            c.setFillColor(ink if bold else muted)
            c.drawRightString(page_w - margin - 30 * mm, yy, label)
            c.drawRightString(page_w - margin, yy, value)
            return yy - 5 * mm

        y = total_line("Taxable Value:", f"Rs. {taxable_total:.2f}", y)
        if show_tax and intra:
            y = total_line(f"CGST @ {settings.gst_cgst_percent}%:", f"Rs. {cgst_total:.2f}", y)
            y = total_line(f"SGST @ {settings.gst_sgst_percent}%:", f"Rs. {sgst_total:.2f}", y)
        elif show_tax:
            y = total_line(f"IGST @ {self._fmt_rate(settings.gst_total_percent)}%:", f"Rs. {igst_total:.2f}", y)
        if discount:
            y = total_line("Discount:", f"- Rs. {discount:.2f}", y)
        if shipping:
            y = total_line("Shipping:", f"Rs. {shipping:.2f}", y)
        y = total_line("GRAND TOTAL:", f"Rs. {grand_total:.2f}", y, bold=True)
        y -= 1 * mm

        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(muted)
        c.drawString(margin, y, f"Amount in words: {amount_in_words_inr(grand_total)}")
        y -= 8 * mm

        # -- Receipt payment block / tax declaration
        if doc_type == "receipt":
            c.setFont("Helvetica-Bold", 8.5)
            c.setFillColor(ink)
            c.drawString(margin, y, "PAYMENT DETAILS:")
            y -= 4.5 * mm
            c.setFont("Helvetica", 8)
            c.setFillColor(muted)
            method = (order_doc.get("payment_method") or "").upper()
            paid = order_doc.get("payment_status") == "completed"
            c.drawString(margin, y, f"Method: {method}  ·  Status: {'RECEIVED' if paid else 'PENDING'}")
            y -= 4 * mm
            if order_doc.get("razorpay_payment_id"):
                c.drawString(margin, y, f"Razorpay Payment ID: {order_doc['razorpay_payment_id']}")
                y -= 4 * mm
            c.drawString(margin, y, f"Amount Received: Rs. {grand_total:.2f}" if paid else "Amount Due on Delivery")
            y -= 8 * mm
        else:
            c.setFont("Helvetica", 8)
            c.setFillColor(muted)
            c.drawString(margin, y, "Whether tax is payable under reverse charge — No")
            y -= 8 * mm

        # -- Footer: declaration + signatory
        c.setStrokeColor(hairline)
        c.line(margin, y, page_w - margin, y)
        y -= 5 * mm
        c.setFont("Helvetica", 7.5)
        c.setFillColor(muted)
        c.drawString(margin, y, "Declaration: Certified that the particulars given above are true and correct.")
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(ink)
        c.drawRightString(page_w - margin, y, f"For {settings.invoice_seller_name}")
        y -= 12 * mm
        c.setFont("Helvetica", 7.5)
        c.setFillColor(muted)
        c.drawRightString(page_w - margin, y, "Authorised Signatory")
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(
            margin, y,
            f"{settings.invoice_brand_name} · {settings.invoice_brand_tagline} · "
            f"This is a computer-generated document.",
        )

        c.showPage()
        c.save()
        return buffer.getvalue()

    @staticmethod
    def _fmt_rate(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)
