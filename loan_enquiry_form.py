from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from datetime import datetime
import csv
import sqlite3
import openai
import re

app = Flask(__name__)
CORS(app)

# Set your OpenAI API key here
openai.api_key = ''

# Create uploads directory if it doesn't exist
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size


@app.route('/')
def serve_frontend():
    """Serve the loan_enquiry_form.html file"""
    return send_from_directory('.', 'loan_enquiry_form.html')


@app.route('/api/status', methods=['GET'])
def api_status():
    """API status check"""
    return jsonify({
        'message': 'Loan Application API is running!',
        'endpoints': {
            'upload': '/upload-audio (POST)',
            'recordings': '/recordings (GET)'
        }
    }), 200


@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    """Handle audio file upload and transcription"""
    try:
        print("\n" + "="*50)
        print("📥 Received audio upload request")
        
        # Check if audio file is in the request
        if 'audio' not in request.files:
            print("✗ No audio file in request")
            return jsonify({'error': 'No audio file provided', 'success': False}), 400
        
        audio_file = request.files['audio']
        
        # Check if file is empty
        if audio_file.filename == '':
            print("✗ Empty filename")
            return jsonify({'error': 'Empty file', 'success': False}), 400
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'recording_{timestamp}.wav'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the audio file
        audio_file.save(filepath)
        
        # Get file size
        file_size = os.path.getsize(filepath)
        
        print(f"✓ Audio saved: {filename} ({file_size / 1024:.2f} KB)")
        
        # Transcribe audio using OpenAI Whisper
        print(f"→ Starting transcription...")
        transcription = transcribe_audio(filepath)
        print(f"✓ Transcription: {transcription}")
        
        # Extract loan application entities
        print(f"→ Extracting loan entities...")
        entities = extract_loan_entities(transcription)
        print(f"✓ Found {len(entities)} entities")
        
        # Print entities for debugging
        for entity in entities:
            print(f"  - {entity['field']}: {entity['value']}")
        
        response_data = {
            'message': 'Audio uploaded and transcribed successfully',
            'filename': filename,
            'size': f'{file_size / 1024:.2f} KB',
            'transcription': transcription,
            'entities': entities,
            'success': True
        }
        
        print(f"✓ Sending response with {len(entities)} entities")
        print("="*50 + "\n")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"✗ Error uploading audio: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'success': False}), 500


def transcribe_audio(filepath):
    """Transcribe audio using OpenAI Whisper API"""
    try:
        with open(filepath, 'rb') as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        return transcript
    except openai.APIError as e:
        error_msg = f"OpenAI API error: {str(e)}"
        print(f"✗ {error_msg}")
        return error_msg
    except openai.AuthenticationError as e:
        error_msg = "Authentication failed. Please check your API key."
        print(f"✗ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Transcription failed: {str(e)}"
        print(f"✗ {error_msg}")
        return error_msg


def extract_loan_entities(text):
    """
    Extract loan application information from transcribed text
    Fields: loan_type, loan_purpose, loan_amount, employment_income, repayment_timeline, bank_relationship
    """
    entities = []
    text_lower = text.lower()
    
    # 1. Extract Loan Type
    loan_types = {
        'personal': ['personal loan', 'personal', 'individual loan'],
        'home': ['home loan', 'housing loan', 'mortgage', 'house loan', 'property loan', 'purchase a home', 'purchase a house'],
        'auto': ['auto loan', 'car loan', 'vehicle loan', 'automobile loan'],
        'business': ['business loan', 'commercial loan', 'enterprise loan', 'business expansion', 'expand my business', 'new business'],
        'education': ['education loan', 'student loan', 'study loan']
    }
    
    for loan_type, keywords in loan_types.items():
        for keyword in keywords:
            if keyword in text_lower:
                entities.append({
                    'field': 'loan_type',
                    'value': loan_type.capitalize() + ' Loan',
                    'confidence': 'high'
                })
                print(f"  ✓ Found Loan Type: {loan_type.capitalize()} Loan")
                break
        if any(entity['field'] == 'loan_type' for entity in entities):
            break
    
    # 2. Extract Loan Purpose
    purpose_keywords = {
        'home_purchase': ['buy home', 'purchase home', 'buying house', 'home purchase', 'buy a house', 'purchase a home', 'purchase a house'],
        'renovation': ['renovation', 'remodel', 'home improvement'],
        'debt_consolidation': ['debt consolidation', 'consolidate debt', 'pay off debts'],
        'business_expansion': ['business expansion', 'expand business', 'grow business'],
        'education': ['education', 'study', 'tuition', 'college', 'tuition fees', 'college fees'],
        'vehicle_purchase': ['buy car', 'purchase vehicle', 'buying car'],
        'medical': ['medical', 'healthcare', 'hospital'],
        'wedding': ['wedding', 'marriage']
    }
    
    for purpose, keywords in purpose_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                purpose_display = purpose.replace('_', ' ').title()
                entities.append({
                    'field': 'loan_purpose',
                    'value': purpose_display,
                    'confidence': 'high'
                })
                print(f"  ✓ Found Loan Purpose: {purpose_display}")
                break
        if any(entity['field'] == 'loan_purpose' for entity in entities):
            break
    
    # 3. Extract Loan Amount (in Rupees)
    # Match patterns like: "₹50,000", "50000 rupees", "50k", "50 thousand", "1 lakh", "10 lakhs", "1 crore"
    amount_patterns = [
        (r'₹\s*(\d{1,3}(?:,\d{3})*)', 'direct'),  # ₹50,000
        (r'(\d+(?:,\d{3})*)\s*(?:rupees?|rs\.?|inr)', 'direct'),  # 50000 rupees
        (r'(\d+(?:\.\d+)?)\s*(?:k|thousand)\s*(?:rupees?|rs\.?)?', 'thousand'),  # 50k or 50 thousand
        (r'(\d+(?:\.\d+)?)\s*(?:lakh|lakhs?)', 'lakh'),  # 1 lakh or 10 lakhs
        (r'(\d+(?:\.\d+)?)\s*(?:crore|crores?)', 'crore')  # 1 crore
    ]
    
    for pattern, conversion_type in amount_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            
            # Convert to rupees based on type
            if conversion_type == 'direct':
                amount = float(amount_str)
            elif conversion_type == 'thousand':
                amount = float(amount_str) * 1000
            elif conversion_type == 'lakh':
                amount = float(amount_str) * 100000
            elif conversion_type == 'crore':
                amount = float(amount_str) * 10000000
            
            # Format in Indian numbering system
            entities.append({
                'field': 'loan_amount',
                'value': f"₹{amount:,.0f}",
                'confidence': 'high'
            })
            print(f"  ✓ Found Loan Amount: ₹{amount:,.0f}")
            break
    
    # 4. Extract Employment and Income Information
    employment_status = None
    income_info = None
    
    # Detect employment status
    employed_keywords = ['employed', 'working', 'job', 'work as', 'working as', 'employed as', 'full time', 'full-time', 'part time', 'part-time', 'am a employee', 'working professional']
    self_employed_keywords = ['self-employed', 'self employed', 'business owner', 'own business', 'freelancer', 'entrepreneur']
    unemployed_keywords = ['unemployed', 'not employed', 'not working', 'no job', 'jobless', 'am not employee']
    
    if any(keyword in text_lower for keyword in self_employed_keywords):
        employment_status = 'Self-Employed'
    elif any(keyword in text_lower for keyword in unemployed_keywords):
        employment_status = 'Unemployed'
    elif any(keyword in text_lower for keyword in employed_keywords):
        employment_status = 'Employed'
    
    # Extract income in rupees (without period)
    income_patterns = [
        (r'(?:salary|income|earn(?:ing)?|make)\s*(?:of|is|around|about)?\s*₹\s*(\d{1,3}(?:,\d{3})*)', 'direct'),
        (r'(?:salary|income|earn(?:ing)?|make)\s*(?:of|is|around|about)?\s*(\d+(?:,\d{3})*)\s*(?:rupees?|rs\.?|inr)', 'direct'),
        (r'(?:salary|income|earn(?:ing)?|make)\s*(?:of|is|around|about)?\s*(\d+(?:\.\d+)?)\s*(?:k|thousand)\s*(?:rupees?|rs\.?)?', 'thousand'),
        (r'(?:salary|income|earn(?:ing)?|make)\s*(?:of|is|around|about)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lakhs?)', 'lakh'),
        (r'(?:salary|income|earn(?:ing)?|make)\s*(?:of|is|around|about)?\s*(\d+(?:\.\d+)?)\s*(?:crore|crores?)', 'crore')
    ]
    
    for pattern, conversion_type in income_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            income_str = match.group(1).replace(',', '')
            
            # Convert to rupees
            if conversion_type == 'direct':
                income = float(income_str)
            elif conversion_type == 'thousand':
                income = float(income_str) * 1000
            elif conversion_type == 'lakh':
                income = float(income_str) * 100000
            elif conversion_type == 'crore':
                income = float(income_str) * 10000000
            
            income_info = f"₹{income:,.0f}"
            break
    
    # Combine employment status and income
    if employment_status or income_info:
        employment_text_parts = []
        
        if employment_status:
            employment_text_parts.append(employment_status)
        
        if income_info:
            employment_text_parts.append(income_info)
        
        employment_text = ' | '.join(employment_text_parts) if employment_text_parts else 'Employed'
        
        entities.append({
            'field': 'employment_income',
            'value': employment_text,
            'confidence': 'medium'
        })
        print(f"  ✓ Found Employment/Income: {employment_text}")
    
    # 5. Extract Repayment Timeline
    timeline_patterns = [
        (r'(\d+)\s*(?:years?|yrs?)', 'years'),
        (r'(\d+)\s*(?:months?|mos?)', 'months'),
        (r'(\d+)\s*to\s*(\d+)\s*(?:years?|yrs?)', 'years_range')
    ]
    
    for pattern, timeline_type in timeline_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if timeline_type == 'years_range':
                timeline_value = f"{match.group(1)}-{match.group(2)} years"
            else:
                timeline_value = f"{match.group(1)} {timeline_type}"
            
            entities.append({
                'field': 'repayment_timeline',
                'value': timeline_value,
                'confidence': 'high'
            })
            print(f"  ✓ Found Repayment Timeline: {timeline_value}")
            break
    
    # 6. Extract Bank Relationship
    relationship_keywords = {
        'yes': ['existing customer', 'current customer', 'already have account', 'have account', 'yes', 'i have account', 'i have account in your bank'],
        'no': ['no account', 'new customer', 'first time', 'no relationship', 'no', "i don't have account", "i don't have account in your bank"]
    }
    
    for relationship, keywords in relationship_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                entities.append({
                    'field': 'bank_relationship',
                    'value': relationship.capitalize(),
                    'confidence': 'medium'
                })
                print(f"  ✓ Found Bank Relationship: {relationship.capitalize()}")
                break
        if any(entity['field'] == 'bank_relationship' for entity in entities):
            break
    
    print(f"  ✓ Total entities extracted: {len(entities)}")
    return entities


@app.route('/recordings', methods=['GET'])
def get_recordings():
    """Get list of all recordings"""
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        recordings = []
        
        for file in files:
            if file.endswith('.wav'):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file)
                file_size = os.path.getsize(filepath)
                recordings.append({
                    'filename': file,
                    'size': f'{file_size / 1024:.2f} KB',
                    'created': datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        return jsonify({
            'count': len(recordings),
            'recordings': recordings
        }), 200
        
    except Exception as e:
        print(f"✗ Error fetching recordings: {str(e)}")
        return jsonify({'error': str(e)}), 500


def _ensure_csv_header(csv_path, headers):
    """Ensure the CSV file exists and has a header row."""
    if not os.path.exists(csv_path):
        try:
            with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            print(f"✓ Created CSV with headers: {csv_path}")
        except Exception as e:
            print(f"✗ Failed to create CSV: {e}")


def _ensure_db(db_path):
    """Create SQLite database and applications table if not exists."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                loanType TEXT,
                loanPurpose TEXT,
                loanAmount TEXT,
                employmentIncome TEXT,
                repaymentTimeline TEXT,
                bankRelationship TEXT,
                transcription TEXT,
                filename TEXT
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"✗ Failed to ensure DB/table: {e}")
    finally:
        try:
            conn.close()
        except:
            pass


@app.route('/submit-application', methods=['POST'])
def submit_application():
    """Receive completed form data (JSON) and append it to a CSV file.

    Expected JSON keys: loanType, loanPurpose, loanAmount, employmentIncome,
    repaymentTimeline, bankRelationship, transcription (optional), filename (optional)
    """
    try:
        data = request.get_json(force=True)

        # Safety: fallback to empty strings if keys missing
        record = {
            'timestamp': datetime.now().isoformat(),
            'loanType': data.get('loanType', '') if data else '',
            'loanPurpose': data.get('loanPurpose', '') if data else '',
            'loanAmount': data.get('loanAmount', '') if data else '',
            'employmentIncome': data.get('employmentIncome', '') if data else '',
            'repaymentTimeline': data.get('repaymentTimeline', '') if data else '',
            'bankRelationship': data.get('bankRelationship', '') if data else '',
            'transcription': data.get('transcription', '') if data else '',
            'filename': data.get('filename', '') if data else ''
        }

        csv_path = os.path.join(app.config['UPLOAD_FOLDER'], 'applications.csv')
        headers = ['timestamp', 'loanType', 'loanPurpose', 'loanAmount', 'employmentIncome', 'repaymentTimeline', 'bankRelationship', 'transcription', 'filename']

        # Ensure header exists
        _ensure_csv_header(csv_path, headers)

        # Append the record
        with open(csv_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([record[h] for h in headers])

        print(f"✓ Application saved to CSV: {csv_path}")

        # Also save into SQLite database
        db_path = os.path.join(app.config['UPLOAD_FOLDER'], 'applications.db')
        try:
            _ensure_db(db_path)
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO applications (timestamp, loanType, loanPurpose, loanAmount, employmentIncome, repaymentTimeline, bankRelationship, transcription, filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (record['timestamp'], record['loanType'], record['loanPurpose'], record['loanAmount'], record['employmentIncome'], record['repaymentTimeline'], record['bankRelationship'], record['transcription'], record['filename'])
            )
            conn.commit()
            conn.close()
            print(f"✓ Application saved to DB: {db_path}")
            db_saved = True
        except Exception as e:
            print(f"✗ Error saving to DB: {e}")
            db_saved = False

        return jsonify({'success': True, 'message': 'Application saved', 'csv': csv_path, 'db_saved': db_saved, 'db': db_path}), 200

    except Exception as e:
        print(f"✗ Error saving application: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("🏦 Voice-based Loan Application System")
    print("=" * 50)
    # print(f"✓ Server running at: http://127.0.0.1:5002")
    # print(f"✓ Upload endpoint: http://127.0.0.1:5000/upload-audio")
    # print(f"✓ Loan fields: Type, Purpose, Amount, Employment, Timeline, Relationship")
    # print(f"✓ Frontend: loan_enquiry_form.html")
    # print("=" * 50)
    # print("Press CTRL+C to stop the server")
    # print("=" * 50)
    app.run(debug=True, port=5002, host='127.0.0.1')