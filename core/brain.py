"""
FieldFlow AI - Brain Module
US Construction Site Voice/Text Analysis Engine

"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


class ConstructionBrain:
    """AI engine for parsing construction site reports into structured JSON."""
    
    def __init__(self):
        """Initialize with OpenAI for both GPT-4o-mini (parsing) and Whisper (transcription)."""
        from openai import OpenAI
        
        # Single OpenAI client for both services
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.openai_client = OpenAI(api_key=api_key)
        
        # Model configuration
        self.llm_model = "gpt-4o-mini"  # Fast, cheap, excellent JSON parsing
        self.whisper_model = "whisper-1"  # Speech-to-text
    
    def get_system_prompt(self):
        """Professional US construction jargon parser prompt."""
        return """You are an expert US construction site engineer and data analyst. 
Your job is to parse field reports from construction foremen into structured JSON for ERP systems like Procore.

## CONSTRUCTION JARGON DICTIONARY:
- "pour" / "placed" / "shot" -> Concrete production
- "rebar" / "reinforcement" / "iron" -> Steel/rebar delivery or installation
- "yards" / "CY" -> Cubic yards (concrete)
- "tons" / "LF" / "SF" -> Tons, Linear feet, Square feet
- "crew" / "guys" / "hands" -> Labor count
- "punch list" / "snag list" -> Deficiency items
- "RFI" -> Request for Information
- "CO" / "change order" -> Budget/scope change
- "grade" / "grading" -> Earthwork
- "form" / "formwork" -> Concrete forming
- "MEP" -> Mechanical/Electrical/Plumbing

## CSI MASTERFORMAT COST CODES:
- 03-30-00: Cast-in-Place Concrete
- 03-20-00: Concrete Reinforcing (Rebar)
- 05-12-00: Structural Steel
- 31-23-00: Excavation & Fill
- 09-91-00: Painting
- 03-05-00: Concrete Materials (Cement, etc.)
- 32-12-00: Asphalt Paving

## OUTPUT JSON FORMAT:
You MUST return a JSON ARRAY containing one or more event objects. If the message describes multiple independent events (e.g. manpower and equipment separately), separate them into multiple objects in the array. If there is only one event, return an array with a single object.
[
  {
    "log_type": "production|materials|delivery|manpower|equipment|safety|notes",
    "description": "Brief professional summary for comments/notes fields",
    "item": "Main item name (Equipment Name, Material Name, Safety Subject, etc.)",
    "quantity": number or null,
    "unit": "CY|tons|LF|SF|EA|hours|null",
    "location": {
      "name": "Full location string (e.g. Building A Level 2)",
      "building": "string or null",
      "level": "string or null", 
      "area": "string or null"
    },
    "cost_code": "XX-XX-XX format",
    
    // MANPOWER SPECIFIC
    "crew": {
      "company_name": "Subcontractor company name if mentioned",
      "count": number or null,
      "hours": number or null,
      "trade": "string or null"
    },

    // EQUIPMENT SPECIFIC
    "equipment_details": {
      "hours_operating": number or null,
      "hours_idle": number or null,
      "inspected": boolean (true if inspection mentioned)
    },

    // DELIVERY SPECIFIC
    "delivery_details": {
      "delivery_from": "Vendor/Supplier name",
      "tracking_number": "string or null",
      "time": "HH:MM format if mentioned",
      "contents": "Description of contents"
    },

    // SAFETY SPECIFIC
    "safety_details": {
      "safety_notice": "Notice details",
      "issued_to": "Person/Company issued to",
      "compliance_due": "YYYY-MM-DD if mentioned"
    },

    "urgency": "normal|high|critical",
    "procore_ready": true
  }
]

## RULES:
1. Always respond with ONLY a valid JSON ARRAY, no extra text or markdown formatting.
2. Use null for missing/unknown values
3. Infer cost codes from context
4. Urgency is "critical" for safety issues, "high" for delays
5. Parse "idle" time distinct from "operating" time for equipment
6. Extract Vendor names for deliveries and subcontractors for manpower checks"""

    def transcribe_audio(self, audio_file_path: str) -> str:
        """
        Transcribe audio file to text using OpenAI Whisper.
        
        Args:
            audio_file_path: Path to audio file (mp3, wav, ogg, m4a, webm)
            
        Returns:
            Transcribed text string
        """
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model=self.whisper_model,
                    file=audio_file,
                    language="en"
                )
            return transcript.text
        except Exception as e:
            raise TranscriptionError(f"Whisper transcription failed: {str(e)}")

    def parse_text(self, text: str) -> dict:
        """
        Parse construction report text into structured JSON.
        Uses OpenRouter API with Meta Llama 3.1 (free tier).
        
        Args:
            text: Raw transcript or typed message
            
        Returns:
            Parsed dictionary with construction data
        """
        try:
            # Call GPT-4o-mini via OpenAI API
            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean up response (remove markdown code blocks if present)
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            raise ParsingError(f"Invalid JSON from LLM: {str(e)}")
        except requests.RequestException as e:
            raise ParsingError(f"OpenRouter API error: {str(e)}")
        except Exception as e:
            raise ParsingError(f"LLM parsing failed: {str(e)}")

    def process_audio(self, audio_file_path: str) -> dict:
        """
        Full pipeline: Audio -> Text -> Structured JSON.
        
        Args:
            audio_file_path: Path to audio file
            
        Returns:
            Dict with 'transcript' and 'parsed_data'
        """
        transcript = self.transcribe_audio(audio_file_path)
        parsed_data = self.parse_text(transcript)
        
        return {
            "transcript": transcript,
            "parsed_data": parsed_data
        }


class TranscriptionError(Exception):
    """Raised when Whisper transcription fails."""
    pass


class ParsingError(Exception):
    """Raised when LLM parsing fails or returns invalid JSON."""
    pass


# --- TEST SECTION ---
if __name__ == "__main__":
    brain = ConstructionBrain()
    
    # Test samples
    test_messages = [
        "Hey boss, we just finished pouring 150 yards of concrete at Building A level 2. Had 8 guys on the crew today, used the pump truck.",
        "20 tons of cement delivered to main gate this morning, unloaded it by the batch plant.",
        "Got a safety issue - the scaffolding on the east side needs inspection before we can continue.",
        "Rebar crew installed 15 tons of reinforcement at the parking deck today. Going smooth."
    ]
    
    print("=" * 60)
    print("FieldFlow AI - Brain Module Test")
    print("=" * 60)
    
    for i, msg in enumerate(test_messages, 1):
        print(f"\n--- Test {i} ---")
        print(f"Input: {msg[:60]}...")
        try:
            result = brain.parse_text(msg)
            print(f"Output: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
