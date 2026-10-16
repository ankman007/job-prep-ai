import pymupdf as fitz
from fastapi import HTTPException
from loguru import logger

def extract_text_from_pdf(file):
    try:
        doc = fitz.open(stream=file.file.read(), filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF file: {e}")
        raise HTTPException(status_code=400, detail="Invalid PDF file")
    
    text = ""
    
    try:
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text += page.get_text()
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        raise HTTPException(status_code=500, detail="Error extracting text from PDF")
    
    if not text:
        logger.warning("No text extracted from the PDF")
        raise HTTPException(status_code=404, detail="No text found in PDF")
    
    return text
