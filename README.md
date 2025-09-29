# Resume-Data-Extractor

This project extracts and analyzes resumes using OpenAI's API. It supports DOCX and PDF formats, validates extracted data, and can optionally integrate with Airtable for storage.

---

## Project Structure
```
Resume-Data-Extractor/
│
├─ .venv/ # Python virtual environment
├─ .env # Environment variables (API keys)
├─ requirements.txt # Python dependencies
├─ src/
│ ├─ airtable_client.py # Handles Airtable integration
│ ├─ llm_client.py # Handles calls to OpenAI models
│ ├─ validators.py # Data validation utilities
│ └─ extract_resume.py # Core resume extraction logic
└─ samples/
└─ resumes/ # Sample resume files (PDF/DOCX)
│ ├─ resume1.docx
│ ├─ resume2.docx
│ └─ resume3.docx
│ ├─ resume4.docx
│ ├─ resume5.docx
```

---

## Setup

1. Clone the repository

```bash
git clone  https://github.com/codeswa1/Resume-Data-Extractor.git
cd Resume-Data-Extractor
```

2. Create a virtual environment
   
```bash
python -m venv .venv
```

3. Activate the virtual environment
   
   On Windows:

```bash
.venv\Scripts\activate
```

   On Mac/Linux:

```bash
source .venv/bin/activate
```

4. Install dependencies
   
```bash
pip install -r requirements.txt
```

5. Configure environment variables
   
Create a .env file with your API keys:

```bash
OPENAI_API_KEY=your_openai_api_key
AIRTABLE_API_KEY=your_airtable_api_key  
AIRTABLE_BASE_ID=your_base_id  
AIRTABLE_TOKEN=your_airtable_api_token
OPENAI_MODEL=gpt-your_model
```

---

## Usage
Extract Resume Data
Run the extraction of a single resume:

```bash
python -m src.extract_resume samples/resumes/resume1.docx
```

Run the extraction of multiple resumes:

```bash
python -m src.extract_resume samples/resumes/
```


The script extracts:
```
-Name
-Contact Information
-Skills
-Experience
-Education
```

---

## Validate Data

Use validators.py to ensure extracted data meets format requirements (e.g., valid email, phone, skills).

---

## Airtable Integration (Optional)

If configured, extracted data can be sent to Airtable using airtable_client.py.

---

**Notes**

```
-Make sure your OpenAI API key has enough quota to process resumes.
-Tested with Python 3.13.
-Supports DOCX and PDF formats (ensure PDF parsing dependencies are installed).
```

---
