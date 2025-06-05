from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json
import datetime
import re
import os
from typing import Dict, List, Optional
import time
import logging
from math import radians, cos, sin, asin, sqrt

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Parksy:
    def __init__(self):
        self.here_api_key = os.getenv('HERE_API_KEY')
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.here_api_key or not self.openrouter_api_key:
            logger.error("Missing API keys: HERE_API_KEY or OPENROUTER_API_KEY not set")
        
        self.here_geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.here_parking_url = "https://discover.search.hereapi.com/v1/discover"
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        
        self.conversations = {}
        
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

    def generate_fallback_spots(self, location: str) -> List[Dict]:
        """Generate fallback parking spots if HERE API fails"""
        city = location.split(',')[0].trim().lower()
        is_edinburgh = city.includes('edinburgh')
        is_leeds = city.includes('leeds')
        
        city_lat = 55.9533 if is_edinburgh else 53.8008 if is_leeds else 51.5074
        city_lng = -3.1883 if is_edinburgh else -1.5491 else -0.1278
        
        return [
            {
                "id": f"fallback_{city}_1",
                "title": f"{city.title()} Central Car Park",
                "address": f"City Centre, {city.title()}",
                "distance": 500,
                "position": {"lat": city_lat + random.uniform(-0.01, 0.01), "lng": city_lng + random.uniform(-0.01, 0.01)},
                "recommendation_score": 85,
                "pricing": {
                    "hourly_rate": "£3.50" if is_edinburgh else "£2.80",
                    "payment_methods": ["Card", "Mobile App", "Cash"],
                    "daily_rate": "£25.00" if is_edinburgh else "£18.00"
                },
                "availability": {"status": "Available", "spaces_available": 50},
                "special_features": ["CCTV", "Pay-and-Display", "Resident Permits"] if is_edinburgh else ["CCTV", "Payment Kiosk"],
                "restrictions": self._get_city_rules(city),
                "uk_specific": True,
                "walking_time": "5 min",
                "type": "Public Car Park",
                "rank": 1
            },
            {
                "id": f"fallback_{city}_2",
                "title": f"{city.title()} Multi-Storey",
                "address": f"Downtown, {city.title()}",
                "distance": 700,
                "position": {"lat": city_lat + random.uniform(-0.01, 0.01), "lng": city_lng + random.uniform(-0.01, 0.01)},
                "recommendation_score": 80,
                "pricing": {
                    "hourly_rate": "£3.00" if is_edinburgh else "£2.50",
                    "payment_methods": ["Card", "Mobile App"],
                    "daily_rate": "£20.00" if is_edinburgh else "£15.00"
                },
                "availability": {"status": "Limited", "spaces_available": 20},
                "special_features": ["Disabled Access", "CCTV"],
                "restrictions": self._get_city_rules(city),
                "uk_specific": True,
                "walking_time": "7 min",
                "type": "Multi-Storey",
                "rank": 2
            },
            {
                "id": f"fallback_{city}_3",
                "title": f"{city.title()} Street Parking",
                "address": f"High Street, {city.title()}",
                "distance": 300,
                "position": {"lat": city_lat + random.uniform(-0.01, 0.01), "lng": city_lng + random.uniform(-0.01, 0.01)},
                "recommendation_score": 75,
                "pricing": {
                    "hourly_rate": "£2.80" if is_edinburgh else "£2.20",
                    "payment_methods": ["Pay & Display", "Mobile App"],
                    "daily_rate": "£12.00" if is_edinburgh else "£10.00"
                },
                "availability": {"status": "Limited", "spaces_available": 10},
                "special_features": ["Pay & Display", "Time Limited"],
                "restrictions": self._get_city_rules(city),
                "uk_specific": True,
                "walking_time": "3 min",
                "type": "On-Street",
                "rank": 3
            },
            {
                "id": f"fallback_{city}_4",
                "title": f"{city.title()} Park & Ride",
                "address": f"Outskirts, {city.title()}",
                "distance": 2000,
                "position": {"lat": city_lat + random.uniform(-0.01, 0.01), "lng": city_lng + random.uniform(-0.01, 0.01)},
                "recommendation_score": 70,
                "pricing": {
                    "hourly_rate": "£1.50",
                    "payment_methods": ["Card", "Cash"],
                    "daily_rate": "£8.00"
                },
                "availability": {"status": "Available", "spaces_available": 200},
                "special_features": ["Bus Connection", "Large Capacity"],
                "restrictions": self._get_city_rules(city),
                "uk_specific": True,
                "walking_time": "20 min",
                "type": "Park & Ride",
                "rank": 4
            }
        ]

    def _get_default_uk_rules(self) -> List[str]:
        """Default UK parking rules"""
        return [
            "Standard UK parking regulations apply",
            "Check local signage for specific restrictions",
            "Payment required during operational hours",
            "Disabled bays are strictly enforced",
            "No parking on double yellow lines"
        ]

    def _get_city_rules(self, city: str) -> List[str]:
        """City-specific UK parking rules"""
        city_lower = city.lower()
        rules = self._get_default_uk_rules()
        
        if 'london' in city_lower:
            rules.extend([
                "Congestion Charge may apply (Mon-Fri, 7am-6pm)",
                "ULEZ charges apply for non-compliant vehicles"
            ])
        elif 'manchester' in city_lower or 'birmingham' in city_lower:
            rules.extend([
                "City centre time limits enforced",
                "Evening restrictions may apply until 8pm"
            ])
        elif 'edinburgh' in city_lower:
            rules.extend([
                "Controlled Parking Zones (CPZs) operate Mon-Fri, 8:30am-6:30pm",
                "Resident permit zones limit non-permit parking to 4 hours",
                "Pay-and-display rates vary by zone (£3-£5/hour in central areas)",
                "Check for event-related restrictions near venues"
            ])
        elif 'leeds' in city_lower:
            rules.extend([
                "Clean Air Zone charges may apply for non-compliant vehicles",
                "City centre parking limited to 2-3 hours in some areas",
                "Evening restrictions in entertainment districts until 8pm"
            ])
        
        return rules

    def geocode_location(self, location: str) -> Optional[Dict]:
        """Convert location string to coordinates using HERE Geocoding API"""
        try:
            params = {
                'q': location,
                'apikey': self.here_api_key,
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
        except requests.RequestException as e:
            logger.error(f"Geocoding error for {location}: {e}")
            return None

    def search_parking(self, lat: float, lng: float, radius: int = 1500) -> List[Dict]:
        """Search for parking spots near coordinates using HERE Discover API"""
        try:
            params = {
                'at': f"{lat},{lng}",
                'limit': 20,
                'q': 'parking facility',
                'apikey': self.here_api_key
            }
            response = requests.get(self.here_parking_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            parking_spots = []
            
            if 'items' in data:
                for spot in data['items']:
                    spot_lat = spot.get('position', {}).get('lat', lat)
                    spot_lng = spot.get('position', {}).get('lng', lng)
                    distance = self._calculate_distance(lat, lng, spot_lat, spot_lng)
                    
                    parking_spots.append({
                        'id': spot.get('id', f"here_{hash(spot['title'])}"),
                        'title': spot.get('title', 'Parking Location'),
                        'address': spot.get('address', {}).get('label', 'Address not available'),
                        'distance': distance,
                        'position': spot.get('position', {'lat': spot_lat, 'lng': spot_lng}),
                        'recommendation_score': 70 + (20 - len(parking_spots)) * 2,
                        'pricing': self._extract_pricing(spot),
                        'availability': {'status': 'Unknown', 'spaces_available': None},
                        'special_features': self._extract_special_features(spot),
                        'restrictions': self._extract_restrictions(spot),
                        'uk_specific': True,
                        'walking_time': f"{max(1, int(distance / 80))} min",
                        'type': spot.get('categories', [{}])[0].get('name', 'Parking Facility'),
                        'rank': len(parking_spots) + 1
                    })
            
            logger.info(f"Found {len(parking_spots)} parking spots for lat={lat}, lng={lng}")
            parking_spots.sort(key=lambda x: x['distance'])
            return parking_spots
        except requests.RequestException as e:
            logger.error(f"Parking search error: {e}")
            return []

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> int:
        """Calculate distance between two points in meters"""
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Radius of earth in meters
        return int(c * r)

    def _extract_pricing(self, spot_data: Dict) -> Dict:
        """Extract pricing information"""
        pricing = {'hourly_rate': 'Unknown', 'payment_methods': ['Card', 'Mobile App']}
        if 'contacts' in spot_data:
            for contact in spot_data['contacts']:
                if 'price' in contact.get('label', '').lower():
                    pricing['hourly_rate'] = contact.get('value', 'Unknown')
        return pricing

    def _extract_restrictions(self, spot_data: Dict) -> List[str]:
        """Extract parking restrictions"""
        restrictions = []
        if 'openingHours' in spot_data and spot_data['openingHours'].get('text'):
            restrictions.append(f"Hours: {spot_data['openingHours']['text']}")
        for category in spot_data.get('categories', []):
            name = category.get('name', '').lower()
            if 'short-term' in name:
                restrictions.append("Short-term parking only")
            elif 'long-term' in name:
                restrictions.append("Long-term parking available")
        return restrictions or ["Check local signage"]

    def _extract_special_features(self, spot_data: Dict) -> List[str]:
        """Extract special features"""
        features = []
        for category in spot_data.get('categories', []):
            name = category.get('name', '').lower()
            if 'accessible' in name:
                features.append("Wheelchair accessible")
            if 'covered' in name:
                features.append("Covered parking")
        if 'contacts' in spot_data:
            for contact in spot_data['contacts']:
                if 'payment' in contact.get('label', '').lower():
                    features.append("Payment kiosk")
        return features or ["CCTV"]

    def generate_ai_response(self, user_input: str, parking_data: List[Dict], location_info: Dict, session_id: str) -> str:
        """Generate AI response using OpenRouter"""
        try:
            conversation_history = self.conversations.get(session_id, [])
            conversation_context = ""
            if conversation_history:
                conversation_context = "Previous conversation:\n"
                for entry in conversation_history[-3:]:
                    conversation_context += f"User: {entry['user']}\nParksy: {entry['assistant']}\n"
                conversation_context += "\n"

            context = f"""
{conversation_context}Current query: {user_input}
Location: {location_info.get('address', 'Unknown') if location_info else 'No specific location'}
Time: {datetime.datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}
Found {len(parking_data)} parking spots.
"""
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": context}
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
            return data['choices'][0]['message']['content'] if data.get('choices') else "Trouble generating response."
        except requests.RequestException as e:
            logger.error(f"AI response error: {e}")
            return f"Found {len(parking_data)} spots, but I'm having trouble with my AI. Check the spots below!"

    def is_parking_related(self, user_input: str) -> bool:
        """Check if input is parking-related"""
        parking_keywords = [
            'park', 'parking', 'spot', 'garage', 'meter', 'valet',
            'car', 'vehicle', 'space', 'lot', 'street', 'curb',
            'ticket', 'fine', 'zone', 'permit', 'handicap', 'disabled'
        ]
        return any(keyword in user_input.lower() for keyword in parking_keywords)

    def extract_location_from_query(self, user_input: str) -> Optional[str]:
        """Extract location from query"""
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
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        
        if self.is_parking_related(user_input) and not self.extract_location_from_query(user_input):
            try:
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"User said: {user_input}\n\nGeneral parking question. Respond as Parksy."}
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
                ai_response = data['choices'][0]['message']['content'] if data.get('choices') else "General response failed."
                self.conversations[session_id].append({'user': user_input, 'assistant': ai_response})
                return {
                    'message': ai_response,
                    'spots': [],
                    'data_status': {'real_time': False, 'last_updated': datetime.datetime.now().isoformat()},
                    'data_sources': {'primary_source': 'OpenRouter', 'real_time_spots': 0, 'enhanced_database_spots': 0}
                }
            except requests.RequestException as e:
                logger.error(f"General chat error: {e}")
                return {
                    'message': "Hey! I'm Parksy. Let's talk parking—what's on your mind?",
                    'spots': [],
                    'data_status': {'real_time': False, 'last_updated': datetime.datetime.now().isoformat()},
                    'data_sources': {'primary_source': 'Fallback', 'real_time_spots': 0, 'enhanced_database_spots': 0}
                }

        location = self.extract_location_from_query(user_input)
        if location:
            location_info = self.geocode_location(location)
            if not location_info:
                ai_response = f"Hmm, I couldn't find '{location}'. Try a more specific address or landmark?"
                self.conversations[session_id].append({'user': user_input, 'assistant': ai_response})
                return {
                    'message': ai_response,
                    'spots': self.generate_fallback_spots(location),
                    'data_status': {'real_time': False, 'last_updated': datetime.datetime.now().isoformat()},
                    'data_sources': {'primary_source': 'Fallback', 'real_time_spots': 0, 'enhanced_database_spots': 4}
                }
            
            parking_data = self.search_parking(location_info['lat'], location_info['lng'])
            if not parking_data:
                logger.warning(f"No parking spots found for {location}")
                parking_data = self.generate_fallback_spots(location)
                source = 'Fallback'
                real_time_spots = 0
                database_spots = len(parking_data)
            else:
                source = 'HERE API'
                real_time_spots = len(parking_data)
                database_spots = 0
            
            ai_response = self.generate_ai_response(user_input, parking_data, location_info, session_id)
            self.conversations[session_id].append({'user': user_input, 'assistant': ai_response})
            
            return {
                'message': ai_response,
                'spots': parking_data,
                'summary': {
                    'total_options': len(parking_data),
                    'average_price': 'Unknown',
                    'closest_option': {'distance': min((spot['distance'] for spot in parking_data), default=0)},
                    'cheapest_option': {'price': 'Unknown'}
                },
                'search_context': {
                    'location': location_info.get('address', location),
                    'local_regulations': self._get_city_rules(location.lower())
                },
                'area_insights': {
                    'area_type': 'Urban',
                    'parking_density': 'Moderate',
                    'typical_pricing': '£2.50/hour',
                    'best_parking_strategy': 'Arrive early'
                },
                'tips': [
                    "Check parking apps for real-time availability",
                    "Avoid peak hours in city centres"
                ],
                'recommendations': {
                    'best_overall': parking_data[0] if parking_data else None,
                    'best_value': parking_data[1] if len(parking_data) > 1 else None,
                    'closest': parking_data[0] if parking_data else None
                },
                'data_status': {
                    'real_time': source == 'HERE API',
                    'last_updated': datetime.datetime.now().isoformat()
                },
                'data_sources': {
                    'primary_source': source,
                    'real_time_spots': real_time_spots,
                    'enhanced_database_spots': database_spots
                }
            }
        
        else:
            try:
                conversation_context = ""
                if self.conversations[session_id]:
                    conversation_context = "Previous conversation:\n"
                    for entry in self.conversations[session_id][-2:]:
                        conversation_context += f"User: {entry['user']}\nParksy: {entry['assistant']}\n"
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"{conversation_context}\nUser said: {user_input}\nRespond as Parksy."}
                ]
                headers = {
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "deepseek/deepseek-r1",
                    "messages": messages,
                    "temperature": 0.8,
                    "max_tokens": 600
                }
                response = requests.post(self.openrouter_url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                ai_response = data['choices'][0]['message']['content'] if data.get('choices') else "Response failed."
                self.conversations[session_id].append({'user': user_input, 'assistant': ai_response})
                return {
                    'message': ai_response,
                    'spots': [],
                    'data_status': {'real_time': False, 'last_updated': datetime.datetime.now().isoformat()},
                    'data_sources': {'primary_source': 'OpenRouter', 'real_time_spots': 0, 'enhanced_database_spots': 0}
                }
            except requests.RequestException as e:
                logger.error(f"Chat error: {e}")
                return {
                    'message': "Hey! I'm Parksy, your parking assistant. What's up?",
                    'spots': [],
                    'data_status': {'real_time': False, 'last_updated': datetime.datetime.now().isoformat()},
                    'data_sources': {'primary_source': 'Fallback', 'real_time_spots': 0, 'enhanced_database_spots': 0}
                }

parksy = Parksy()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id', 'web_session')
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        response = parksy.process_query(user_message, session_id)
        return jsonify(response)
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'Parksy AI',
        'version': '1.0.0',
        'timestamp': datetime.datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
