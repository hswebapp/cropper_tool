
import io
import os
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from pdf2image import convert_from_bytes
import numpy as np
import cv2
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image

app = Flask(__name__)
# ✅ initialize CORS correctly
CORS(app, resources={r"/*": {"origins": "*"}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["POST", "OPTIONS"])

# -------------------- Helper: Decrypt PDF if needed --------------------
def decrypt_pdf_if_needed(pdf_bytes, password=None):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.is_encrypted:
        return pdf_bytes
    try:
        res = reader.decrypt(password or "")
        if res == 0:
            return None
        writer = PdfWriter()
        for p in reader.pages:
            writer.add_page(p)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return None

# -------------------- Aadhaar Card Crop Function --------------------
def crop_bottom_half(pil_img, crop_ratio=0.45):
    """Crops the bottom part of Aadhaar PDF where the actual card exists."""
    img = np.array(pil_img.convert("RGB"))
    h, w, _ = img.shape

    # keep bottom X% of the image
    start_y = int(h * (1 - crop_ratio))
    cropped = img[start_y:h, 0:w]

    # remove any small white margins around
    gray = cv2.cvtColor(cropped, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(mask)
    if coords is not None:
        x, y, w2, h2 = cv2.boundingRect(coords)
        cropped = cropped[y:y+h2, x:x+w2]

    return Image.fromarray(cropped)

# -------------------- Flask Endpoint --------------------

@app.route("/crop_aadhaar", methods=["POST", "OPTIONS"])

def crop_aadhaar():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    pdf_bytes = file.read()

    pdf_bytes = decrypt_pdf_if_needed(pdf_bytes, password)
    if pdf_bytes is None:
        return jsonify({"error": "Invalid or password-protected PDF"}), 401

    try:
        pages = convert_from_bytes(pdf_bytes, dpi=200)
    except Exception as e:
        return jsonify({"error": f"PDF to image conversion failed: {str(e)}"}), 500

    cropped_imgs = []
    for idx, page in enumerate(pages, 1):
        cropped = crop_bottom_half(page, crop_ratio=0.298)  # adjust ratio if needed
        cropped_imgs.append((f"aadhaar_page_{idx}.png", cropped))

    if len(cropped_imgs) == 1:
        buf = io.BytesIO()
        cropped_imgs[0][1].save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png",
                         as_attachment=True,
                         download_name=cropped_imgs[0][0])

    import zipfile
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w') as zf:
        for fname, img in cropped_imgs:
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            zf.writestr(fname, img_bytes.read())
    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True,
                     download_name="aadhaar_cropped.zip")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
