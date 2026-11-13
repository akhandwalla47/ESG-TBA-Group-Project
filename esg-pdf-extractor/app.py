

from flask import Flask, request, jsonify
import fitz
import base64
import os

app = Flask(__name__)

API_KEY = os.environ.get("PDF_API_KEY")

@app.route("/extract-pages", methods=["POST"])
def extract_pages():

    # Check API authentication
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json()

    pdf_base64 = data.get("pdf_base64")
    pages = data.get("pages")

    if not pdf_base64 or not isinstance(pages, list):
        return jsonify({"error": "Missing PDF or page numbers"}), 400

    try:
        # Remove data URL prefix if one is supplied
        if "," in pdf_base64:
            pdf_base64 = pdf_base64.split(",", 1)[1]

        pdf_bytes = base64.b64decode(pdf_base64)

        document = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        # Validate page numbers
        pages = sorted(set(int(page) for page in pages))

        if not pages or any(
            page < 1 or page > document.page_count
            for page in pages
        ):
            return jsonify({
                "error": "Invalid page numbers",
                "total_pages": document.page_count
            }), 400

        output = fitz.open()

        for page in pages:
            output.insert_pdf(
                document,
                from_page=page - 1,
                to_page=page - 1
            )

        result = output.tobytes()

        return jsonify({
            "pdf_base64": base64.b64encode(result).decode("utf-8"),
            "pages_extracted": pages,
            "total_pages_in_original": document.page_count
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
