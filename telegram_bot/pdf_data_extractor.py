# ... existing imports ...
import fitz  # PyMuPDF

# New function to extract text from PDF using PyMuPDF
def extract_pdf_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        if not text:
            raise ValueError("No text extracted from the PDF.")
        return text
    except FileNotFoundError as e:
        print("File not found:", e)
    except ValueError as ve:
        print("Value error:", ve)
    except Exception as e:
        print("An error occurred:", e)

# Example usage
pdf_path = r'E:\JOB.ai\JOB.ai\job_resume\a-customised-curve-cv.pdf'
pdf_text = extract_pdf_text(pdf_path)
