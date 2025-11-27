
import io
import os
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from pdf2image import convert_from_bytes
import numpy as np
import cv2
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import pikepdf

app = Flask(__name__)
# ✅ initialize CORS correctly
CORS(app, resources={r"/*": {"origins": "*"}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["POST", "OPTIONS"])

# -------------------- Helper: Decrypt PDF if needed --------------------

def decrypt_pdf_if_needed(pdf_bytes, password):
    """
    Returns decrypted PDF bytes if needed.
    If PDF is not encrypted → returns original bytes.
    If encrypted and password correct → returns decrypted bytes.
    If encrypted and password wrong → returns None.
    """

    try:
        # Try opening normally first (non-encrypted PDF will work)
        with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
            print("PDF IS NOT ENCRYPTED")
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()

    except pikepdf.PasswordError:
        # PDF is encrypted → try decrypting with given password
        print("PDF IS ENCRYPTED, TRYING PROVIDED PASSWORD...")
        try:
            with pikepdf.open(io.BytesIO(pdf_bytes), password=password) as pdf:
                out = io.BytesIO()
                pdf.save(out)
                print("DECRYPTED SUCCESSFULLY")
                return out.getvalue()
        except Exception:
            print("WRONG PASSWORD")
            return None

    except Exception as e:
        print("UNKNOWN ERROR:", e)
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

# -------------------- Dynamic Cropper --------------------
def crop_image(img, top=0, bottom=0, left=0, right=0):
    """
    Crop percentages from each side.
    Example: bottom=0.25 → remove 25% from bottom.
    """

    width, height = img.size

    # Convert percentage → pixels
    crop_top = int(height * top)
    crop_bottom = height - int(height * bottom)
    crop_left = int(width * left)
    crop_right = width - int(width * right)

    # Ensure valid region
    if crop_bottom <= crop_top or crop_right <= crop_left:
        raise ValueError("Invalid crop settings.")

    return img.crop((crop_left, crop_top, crop_right, crop_bottom))

# -------------------- Flask Endpoint --------------------

@app.route("/", methods=["GET", "OPTIONS"])

def home():    
    return jsonify({"message": "your app is running........."}), 200

@app.route("/crop_aadhaar", methods=["POST", "OPTIONS"])

def crop_aadhaar():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)
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
        cropped = crop_bottom_half(page, crop_ratio=0.283)  # adjust ratio if needed
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


@app.route("/crop_pan", methods=["POST", "OPTIONS"])

def crop_pan():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)

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
        
        cropped = crop_image(
                                page,
                                top=0.768,        # remove 0.768 from top
                                bottom=0.045,     # remove 0.045 from bottom
                                left=0.10,       # remove 10% from left
                                right=0.07       # remove 7% from right
                            )# adjust ratio if needed
        cropped_imgs.append((f"pan_page_{idx}.png", cropped))

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
                     download_name="pancard_cropped.zip")



@app.route("/crop_eshram", methods=["POST", "OPTIONS"])

def crop_eshram():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)

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
        cropped = crop_image(
                                page,
                                top=0.07,        # remove 0.07 from top
                                bottom=0.46,     # remove 0.46 from bottom
                                left=0.23,       # remove 0.23 from left
                                right=0.28       # remove 0.28 from right
                            )# adjust ratio if needed
        cropped_imgs.append((f"eshram_page_{idx}.png", cropped))

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
                     download_name="eshram_cropped.zip")

@app.route("/crop_voterid", methods=["POST", "OPTIONS"])

def crop_voterid():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)

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
        cropped = crop_image(
                                page,
                                top=0.08,        # remove 0.07 from top
                                bottom=0.67,     # remove 0.46 from bottom
                                left=0.05,       # remove 0.23 from left
                                right=0.03       # remove 0.28 from right
                            )# adjust ratio if needed
        cropped_imgs.append((f"voterid_page{idx}.png", cropped))

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
                     download_name="voterid_cropped.zip")

@app.route("/crop_abha", methods=["POST", "OPTIONS"])

def crop_abha():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)

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
        cropped = crop_image(
                                page,
                                top=0.00,        # remove 0.00 from top
                                bottom=0.50,     # remove 0.50 from bottom
                                left=0.00,       # remove 0.00 from left
                                right=0.00       # remove 0.00 from right
                            )# adjust ratio if needed
        cropped_imgs.append((f"abha_page{idx}.png", cropped))

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
                     download_name="abha_cropped.zip")

@app.route("/crop_udid", methods=["POST", "OPTIONS"])

def crop_udid():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)

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
        cropped = crop_image(
                                page,
                                top=0.05,        # remove 0.05 from top
                                bottom=0.54,     # remove 0.54 from bottom
                                left=0.07,       # remove 0.07 from left
                                right=0.47       # remove 0.47 from right
                            )# adjust ratio if needed
        cropped_imgs.append((f"udid_page{idx}.png", cropped))

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
                     download_name="udid_cropped.zip")


@app.route("/crop_uan", methods=["POST", "OPTIONS"])

def crop_uan():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file"}), 400

    file = request.files['file']
    password = request.form.get("password")
    print("PASSWORD RECEIVED:", password)

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
        cropped = crop_image(
                                page,
                                top=0.025,        # remove 0.025 from top
                                bottom=0.50,     # remove 0.50 from bottom
                                left=0.02,       # remove 0.02 from left
                                right=0.02       # remove 0.02 from right
                            )# adjust ratio if needed
        cropped_imgs.append((f"uan_page{idx}.png", cropped))

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
                     download_name="uan_cropped.zip")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
