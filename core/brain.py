"""
RapidSite AI - Brain Module
US Construction Site Voice/Text Analysis Engine

"""

import os
import json
import requests
from dotenv import load_dotenv
from core.utils import retry_on_exception

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
    
    def get_system_prompt(self, company: dict = None):
        """Professional US construction jargon parser prompt."""
        base_prompt = """You are an expert US construction site engineer and data analyst. 
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
    "status": "complete|incomplete",
    "follow_up_question": "string (Turkish, ONLY if status is incomplete) or null",
    "translated_transcript": "Direct English translation of the source message",
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
6. Extract Vendor names for deliveries and subcontractors for manpower checks
7. CRITICAL - MISSING INFO CHECK: If a REQUIRED field for the log_type is missing from the message, set "status": "incomplete" and write a friendly follow_up_question in Turkish asking for the specific missing info.
   - For 'manpower': Requires worker count and hours.
   - For 'equipment': Requires hours_operating.
   - For 'delivery': Requires item and quantity.
   If all required info is present, set "status": "complete" and follow_up_question to null.
   IMPORTANT EXCEPTION: If the input is written in shorthand or telegraphic style (e.g., "4 guys. 8 hrs.", "20 tons"), and logically implies the required data, DO NOT mark it as incomplete. Be smart about parsing numbers.
8. TRANSLATE TO ENGLISH: ALL output text fields (such as 'description', 'item', 'safety_notice', 'contents') MUST be translated into Professional US Construction English, regardless of the input language."""
        
        # Inject Procore Master Data (Fuzzy Matching constraint) if available
        if company:
            vendors = company.get('procore_vendors')
            cost_codes = company.get('procore_cost_codes')
            locations = company.get('procore_locations')
            
            master_data_prompt = "\n\n## MASTER DATA (CRITICAL STRICT MATCHING):\n"
            master_data_prompt += "You MUST map the identified company, cost code, and location to ONE of the exact names/codes provided below. Use your best fuzzy matching judgment. If there is absolutely no reasonable match, you MUST use null. NEVER invent or hallucinate a new vendor or location that is not in this list. It is better to use null than to make up a value.\n"
            
            if vendors and vendors != "[]":
                master_data_prompt += f"\n- VALID VENDORS: {vendors}"
            if cost_codes and cost_codes != "[]":
                master_data_prompt += f"\n- VALID COST CODES: {cost_codes}"
            if locations and locations != "[]":
                master_data_prompt += f"\n- VALID LOCATIONS: {locations}"
                
            if "VALID" in master_data_prompt:
                base_prompt += master_data_prompt
                
        return base_prompt

    @retry_on_exception(exceptions=(Exception,), max_retries=3, initial_delay=1.0)
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
                    file=audio_file
                )
            return transcript.text
        except Exception as e:
            raise TranscriptionError(f"Whisper transcription failed: {str(e)}")

    @retry_on_exception(exceptions=(Exception,), max_retries=3, initial_delay=1.0)
    def parse_text(self, text: str, company: dict = None) -> dict:
        """
        Parse construction report text into structured JSON.
        Uses GPT-4o-mini API.
        
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
                    {"role": "system", "content": self.get_system_prompt(company)},
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

    def process_audio(self, audio_file_path: str, company: dict = None) -> dict:
        """
        Full pipeline: Audio -> Text -> Structured JSON.
        
        Args:
            audio_file_path: Path to audio file
            company: Company dict for Procore metadata context
            
        Returns:
            Dict with 'transcript' and 'parsed_data'
        """
        transcript = self.transcribe_audio(audio_file_path)
        parsed_data = self.parse_text(transcript, company=company)
        
        return {
            "transcript": transcript,
            "parsed_data": parsed_data
        }


    @retry_on_exception(exceptions=(Exception,), max_retries=3, initial_delay=1.0)
    def resolve_incomplete(self, incomplete_json: dict, new_text: str, company: dict = None) -> dict:
        """
        Intelligently resolves an incomplete report with new user input.
        Returns a JSON with 'updated_incomplete_event' (if it answers the question)
        and 'new_events' (if the input contains new, unrelated reports).
        """
        try:
            # Re-use the master data logic if available
            master_data_prompt = ""
            if company:
                vendors = company.get('procore_vendors')
                cost_codes = company.get('procore_cost_codes')
                locations = company.get('procore_locations')
                
                master_data_prompt = "\n\n## MASTER DATA (CRITICAL STRICT MATCHING):\n"
                master_data_prompt += "Map any identified company, cost code, and location to ONE of the exact names/codes provided below. If there is absolutely no reasonable match, use null.\n"
                
                if vendors and vendors != "[]":
                    master_data_prompt += f"- VALID VENDORS: {vendors}\n"
                if cost_codes and cost_codes != "[]":
                    master_data_prompt += f"- VALID COST CODES: {cost_codes}\n"
                if locations and locations != "[]":
                    master_data_prompt += f"- VALID LOCATIONS: {locations}\n"
                    
                if "- VALID" not in master_data_prompt:
                    master_data_prompt = ""
            
            system_prompt = f"""You are an expert US construction site data parser.
The user previously sent an incomplete report that is missing some information.
The incomplete report JSON is:
{json.dumps(incomplete_json, ensure_ascii=False, indent=2)}

The user just sent a NEW MESSAGE: "{new_text}"

YOUR TASK:
1. Determine if the NEW MESSAGE provides the missing information for the incomplete report.
2. If it DOES, update the incomplete report JSON with the new information. If the required fields are now present, change its "status" to "complete" and "follow_up_question" to null.
3. If it DOES NOT, or if the new message ALSO contains completely new and unrelated construction events (e.g. a new delivery, a different crew, a safety issue), parse those new events into a separate list.
4. If the new message is COMPLETELY UNRELATED to the incomplete report, leave "updated_incomplete_event" as null.

{master_data_prompt}

## OUTPUT JSON FORMAT:
You MUST return ONLY a valid JSON object with the following exact structure:
{{
  "updated_incomplete_event": {{ ... updated json of the old report ... }} or null,
  "new_events": [ {{ ... new event json ... }}, {{ ... another new event ... }} ] or []
}}

For "new_events", follow the standard output schema (log_type, item, quantity, unit, cost_code, etc.) and translate output text to US Construction English.
If the user's input is telegraphic/shorthand but implies the required info (like "4 guys. 8 hrs."), be smart and do not mark it incomplete.
"""

            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            
            return json.loads(content)
            
        except Exception as e:
            raise ParsingError(f"LLM resolve_incomplete failed: {str(e)}")


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
    print("RapidSite AI - Brain Module Test")
    print("=" * 60)
    
    for i, msg in enumerate(test_messages, 1):
        print(f"\n--- Test {i} ---")
        print(f"Input: {msg[:60]}...")
        try:
            result = brain.parse_text(msg)
            print(f"Output: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
