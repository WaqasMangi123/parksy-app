from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json
import datetime
import re
import os
from typing import Dict, List, Optional
import logging

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Parksy:
    def __init__(self):
        # Get API keys from environment variables (secure for deployment)
        self.here_api_key = os.getenv('HERE_API_KEY')
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.here_api_key or not self.openrouter_api_key:
            logger.error("Missing API keys: HERE_API_KEY or OPENROUTER_API_KEY not set")
            raise ValueError("API keys must be set in environment variables")
        
        # API Endpoints
        self.here_geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.here_parking_url = "https://discover.search.hereapi.com/v1/discover"
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Conversation sessions (in production, use Redis or database)
        self.conversations = {}
        
        # Enhanced system prompt for Parksy
        self.system_prompt = """You are Parksy, a friendly AI parking assistant who talks like a real person. You're knowledgeable, conversational, and genuinely want to help people with their parking struggles.

Key traits:
- You're called Parksy - embrace it! Be personable and memorable
- Respond naturally to whatever users say, never force them into specific formats
- Use casual, human language with contractions and conversational phrases
- Show empathy for parking struggles (everyone hates finding parking!)
- Adapt your response style to match the user's tone and urgency
- Remember context from your conversation with each user
- Be encouraging, positive, and sometimes a bit cheeky
- Use real parking data when available, present it clearly but don't overwhelm

Response guidelines:
- Always acknowledge what they're asking about first
- If you have parking data, present it in a helpful, scannable way
- Give practical, local advice and suggestions
- Be personal - use "you" and "I" naturally
- If they're frustrated, be understanding and supportive
- If they're in a hurry, be concise and action-oriented
- If they want to chat, be conversational and fun

Remember: You're Parksy, the parking assistant people actually want to talk to. Make finding parking a little less painful! 🅿️"""

    def geocode_location(self, location: str) -> Optional[Dict]:
        """Convert location string to coordinates using HERE Geocoding API"""
        try:
            params = {
                'q': location,
                'apiKey': self.here_api_key,  # Updated to match HERE API
                'limit': 1
            }
            
            response = requests.get(self.here_geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('items'):
                item = data['items'][0]
                return {
                    'lat': item['position']['lat'],
                    'lng': item['position']['lng'],
                    'address': item['address']['label']
                }
            logger.warning(f"No geocoding results for location: {location}")
            return None
            
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            return None

    def search_parking(self, lat: float, lng: float, radius: int = 1500) -> List[Dict]:
        """Search for parking spots near given coordinates using HERE Discover API"""
        try:
            params = {
                'at': f"{lat},{lng}",
                'limit': 20,
                'q': 'parking',
                'apiKey': self.here_api_key  # Updated to match HERE API
            }
            
            response = requests.get(self.here_parking_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            parking_spots = []
            
            if 'items' in data:
                for spot in data['items']:
                    spot_lat = spot.get('position', {}).get('lat', 0)
                    spot_lng = spot.get('position', {}).get('lng', 0)
                    distance = self._calculate_distance(lat, lng, spot_lat, spot_lng)
                    
                    parking_info = {
                        'name': spot.get('title', 'Parking Location'),
                        'address': spot.get('address', {}).get('label', 'Address not available'),
                        'distance': distance,
                        'position': spot.get('position', {}),
                        'categories Matthew: categories': spot.get('categories', []),
                        'openingHours': spot.get('openingHours', {}),
                        'pricing': self._extract_pricing(spot),
                        'restrictions': self._extract_restrictions(spot),
                        'payment_methods': self._extract_payment_methods(spot),
                        'accessibility': self._extract_accessibility(spot),
                        'contacts': spot.get('contacts', [])
                    }
                    parking_spots.append(parking_info)
            
            parking_spots.sort(key=lambda x: x['distance'])
            logger.info(f"Found {len(parking_spots)} parking spots for lat={lat}, lng={lng}")
            return parking_spots
            
        except Exception as e:
            logger.error(f"Parking search error: {e}")
            return []

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> int:
        """Calculate distance between two points in meters"""
        from math import radians, cos, sin, asin, sqrt
        
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Radius of earth in meters
        
        return int(c * r)

    def _extract_pricing(self, spot_data: Dict) -> Dict:
        """Extract pricing information from parking spot data"""
        pricing = {}
        if 'contacts' in spot_data:
            for contact in spot_data['contacts']:
                if contact.get('label') == 'Price':
                    pricing['info'] = contact.get('value', '')
        return pricing

    def _extract_restrictions(self, spot_data: Dict) -> List[str]:
        """Extract parking restrictions from spot data"""
        restrictions = []
        
        if 'openingHours' in spot_data:
            opening_hours = spot_data['openingHours']
            if 'text' in opening_hours:
                restrictions.append(f"Hours: {opening_hours['text']}")
        
        categories = spot_data.get('categories', [])
        for category in categories:
            if 'parking' in category.get('name', '').lower():
                if 'short-term' in category.get('name', '').lower():
                    restrictions.append("Short-term parking only")
                elif 'long-term' in category.get('name', '').lower():
                    restrictions.append("Long-term parking available")
        
        return restrictions

    def _extract_payment_methods(self, spot_data: Dict) -> List[str]:
        """Extract payment method information"""
        payment_methods = []
        
        if 'contacts' in spot_data:
            for contact in spot_data['contacts']:
                if 'payment' in contact.get('label', '').lower():
                    payment_methods.append(contact.get('value', ''))
        
        return payment_methods if payment_methods else ["Payment info not available"]

    def _extract_accessibility(self, spot_data: Dict) -> List[str]:
        """Extract accessibility information"""
        accessibility = []
        
        categories = spot_data.get('categories', [])
        for category in categories:
            if 'accessible' in category.get('name', '').lower():
                accessibility.append("Wheelchair accessible")
        
        return accessibility

    def generate_ai_response(self, user_input: str, parking_data: List[Dict], location_info: Dict, session_id: str) -> str:
        """Generate AI response using DeepSeek R1 via OpenRouter"""
        try:
            # Get conversation history for this session
            conversation_history = self.conversations.get(session_id, [])
            
            # Build conversation context
            conversation_context = ""
            if conversation_history:
                conversation_context = "Previous conversation:\n"
                for entry in conversation_history[-3:]:
                    conversation_context += f"User: {entry['user']}\nParksy: {entry['assistant']}\n"
                conversation_context += "\n"

            # Prepare context with parking data
            context = f"""
{conversation_context}Current query: {user_input}

Location searched: {location_info.get('address', 'Unknown location') if location_info else 'No specific location'}
Current time: {datetime.datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}

"""
            
            if parking_data:
                context += f"Found {len(parking_data)} parking options:\n\n"
                for i, spot in enumerate(parking_data, 1):
                    distance_text = f"{spot['distance']}m" if spot['distance'] < 1000 else f"{spot['distance']/1000:.1f}km"
                    context += f"{i}. {spot['name']}\n"
                    context += f"   📍 {spot['address']}\n"
                    context += f"   🚶 {distance_text} away\n"
                    
                    if spot['restrictions']:
                        context += f"   ⏰ {', '.join(spot['restrictions'])}\n"
                    
                    if spot['pricing'].get('info'):
                        context += f"   💰 {spot['pricing']['info']}\n"
                    
                    if spot['accessibility']:
                        context += f"   ♿ {', '.join(spot['accessibility'])}\n"
                    
                    context += "\n"
            else:
                context += "No parking spots found in the searched area.\n"

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": context
                }
            ]
            
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek/deepseek-r1",
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 1500,
                "top_p": 0.9
            }
            
            response = requests.post(self.openrouter_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'choices' in data and data['choices']:
                return data['choices'][0]['message']['content']
            
            return "Hey! I'm having a bit of trouble right now, but let me try to help you with what I found!"
            
        except Exception as e:
            logger.error(f"AI response error: {e}")
            if parking_data:
                return f"I found {len(parking_data)} parking options for you, but I'm having trouble with my response system. The parking data should still be helpful!"
            return "I'm having some technical difficulties right now. Could you try asking everything again?"

    def is_parking_related(self, user_input: str) -> bool:
        """Check if user input is parking-related"""
        parking_keywords = [
            'park', 'parking', 'spot', 'garage', 'meter', 'valet',
            'car', 'vehicle', 'space', 'lot', 'street', 'curb',
            'ticket', 'fine', 'zone', 'permit', 'handicap', 'disabled'
        ]
        
        user_lower = user_input.lower()
        return any(keyword in user_lower for keyword in parking_keywords)

    def extract_location_from_query(self, user_input: str) -> Optional[str]:
        """Extract location from user query using improved patterns"""
        patterns = [
            r"(?:at|near|in|around|by|close to|next to)\s+([^?.,!]+?)(?:\s+(?:at|for|during)|\s*[?.,!]|$)",
            r"park\s+(?:at|near|in|around|by|close to|next to)\s+([^?.,!]+?)(?:\s+(?:at|for|during)|\s*[?.,!]|$)",
            r"parking\s+(?:at|near|in|around|by|close to|next to)\s+([^?.,!]+?)(?:\s+(?:at|for|during)|\s*[?.,!]|$)",
            r"(?:where|how|can)\s+.*?(?:at|near|in|around|by)\s+([^?.,!]+?)(?:\s*[?.,!]|$)",
            r"going\s+to\s+([^?.,!]+?)(?:\s+(?:at|for|during)|\s*[?.,!]|$)",
            r"visiting\s+([^?.,!]+?)(?:\s+(?:at|for|during)|\s*[?.,!]|$)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                if location.lower() not in ['there', 'here', 'it', 'this', 'that', 'a', 'the']:
                    return location
        
        return None

    def process_query(self, user_input: str, session_id: str = "default") -> Dict:
        """Process user query and return structured response"""
        # Initialize session if needed
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        # Limit conversation history to prevent memory issues
        if len(self.conversations[session_id]) > 5:
            self.conversations[session_id] = self.conversations[session_id][-5:]
        
        # Handle general parking conversation
        if self.is_parking_related(user_input) and not self.extract_location_from_query(user_input):
            try:
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"User said: {user_input}\n\nThis seems to be a general parking question or comment. Respond naturally as Parksy, even though no specific location was mentioned."}
                ]
                
                headers = {
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "deepseek/deepseek-r1",
                    "messages": messages,
                    "temperature": 0.8,
                    "max_tokens": 800
                }
                
                response = requests.post(self.openrouter_url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                if 'choices' in data and data['choices']:
                    ai_response = data['choices'][0]['message']['content']
                    self.conversations[session_id].append({'user': user_input, 'assistant': ai_response})
                    return {
                        'response': ai_response,
                        'spots': [],
                        'session_id': session_id,
                        'timestamp': datetime.datetime.now().isoformat()
                    }
                    
            except Exception as e:
                logger.error(f"General chat error: {e}")
                return {
                    'response': "Hey! I'm Parksy. Let's talk parking—what's on your mind?",
                    'spots': [],
                    'session_id': session_id,
                    'timestamp': datetime.datetime.now().isoformat()
                }
        
        # Extract location for specific searches
        location = self.extract_location_from_query(user_input)
        
        if location:
            # Geocode the location
            location_info = self.geocode_location(location)
            if not location_info:
                response = f"Hmm, I'm having trouble finding '{location}'. Could you be a bit more specific? Maybe include a street address or a well-known landmark?"
                self.conversations[session_id].append({'user': user_input, 'assistant': response})
                return {
                    'response': response,
                    'spots': [],
                    'session_id': session_id,
                    'timestamp': datetime.datetime.now().isoformat()
                }
            
            # Search for parking
            parking_data = self.search_parking(location_info['lat'], location_info['lng'])
            
            # Generate AI response
            ai_response = self.generate_ai_response(user_input, parking_data, location_info, session_id)
            self.conversations[session_id].append({'user': user_input, 'assistant': ai_response})
            return {
                'response': ai_response,
                'spots': parking_data,
                'session_id': session_id,
                'timestamp': datetime.datetime.now().isoformat()
            }
        
        else:
            # Handle non-parking or unclear queries
            try:
                conversation_history = self.conversations[session_id]
                conversation_context = ""
                if conversation_history:
                    conversation_context = "Previous conversation:\n"
                    for entry in conversation_history[-2:]:
                        conversation_context += f"User: {entry['user']}\nParksy: {entry['assistant']}\n"

                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"{conversation_context}\nUser just said: {user_input}\n\nRespond naturally as Parksy to whatever they're saying. If it's not parking-related, gently steer toward how you can help with parking, but don't be pushy."}
                ]
                
                headers = {
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model "

parksy = Parksy()

# Flask Routes
@app.route('/')
def index():
    """Serve the main chat interface"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages via API"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id', 'web_session')
        
        if not user_message:
            return jsonify({'error': 'No  message provided'}), 400
        
        response = parksy.process_query(user_message, session_id)
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'Parksy AI',
        'version': '1.0.0',
        'timestamp': datetime.datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
