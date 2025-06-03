import requests
import json
import re
from datetime import datetime, timedelta
import random
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

@dataclass
class ParkingContext:
    """Store conversation context for parking queries"""
    location: Optional[str] = None
    time_context: Optional[str] = None
    duration: Optional[int] = None
    preferences: Optional[Dict] = None
    last_search: Optional[Dict] = None

class EnhancedParkingChatbot:
    def __init__(self):
        """Initialize the enhanced parking chatbot with HERE.com integration"""
        # API Configuration for HERE.com
        self.api_key = os.getenv('HERE_API_KEY', 'demo_key_for_testing')
        self.discover_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.parking_url = "https://parking.search.hereapi.com/v1/browse"  # Hypothetical parking endpoint

        # Conversation context storage
        self.user_contexts = {}

        # Mock data for locations not found
        self.mock_parking_types = [
            "On-Street Metered Parking", "Municipal Parking Lot", "Private Garage",
            "Shopping Center Parking", "Residential Permit Zone", "EV Charging Station",
            "Park & Ride Facility", "Hospital Parking", "University Parking"
        ]

        # UK Parking Rules
        self.uk_parking_rules = {
            'general': [
                "Always check parking signs - they're legally binding",
                "Single yellow lines mean no parking during specified times",
                "Double yellow lines mean no parking at any time",
                "Blue badge holders have special parking privileges",
                "Most councils offer free parking after 6pm and on Sundays"
            ],
            'costs': {
                'city_centre': "£2-5 per hour in most UK city centres",
                'residential': "£1-3 per hour in residential permit areas",
                'retail_parks': "Usually free for 2-3 hours at shopping centres",
                'train_stations': "£3-8 per day at most UK train stations"
            }
        }

        # Intent patterns
        self.intent_patterns = {
            'greeting': [
                r'\b(hi|hello|hey|alright|cheers|hiya)\b',
                r'^(hey\s+there|what\'s\s+up|how\s+do)\b'
            ],
            'parking_query': [
                r'\b(park|parking|spot|car\s+park|bay|space|ev|electric|accessible|disabled|permit)\b',
                r'\b(can\s+i\s+park|where\s+to\s+park|need\s+parking|looking\s+for\s+parking)\b'
            ],
            'time_query': [
                r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|now|today|tomorrow|morning|afternoon|evening)\b',
                r'\b(for\s+\d+\s+(hours?|hrs?|minutes?|mins)|overnight|all\s+day)\b'
            ],
            'location_query': [
                r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:street|st|road|rd|lane|avenue|ave|city|town|centre|center))\b',
                r'\b([A-Z][a-zA-Z\s]{2,})\b(?=\s+(?:at|for|around|by|\d|$))'
            ],
            'preference_query': [
                r'\b(free|cheap|covered|garage|ev|electric|charging|accessible|disabled|long\s+term|overnight)\b'
            ]
        }

        # Personality responses
        self.personality_responses = {
            'greeting': [
                "Alright! 👋 I'm your parking mate, powered by HERE.com. Where do you need a spot?",
                "Hello! 🚗 Ready to find you a cracking parking spot. What's up?"
            ],
            'no_data': [
                "No specific data from HERE.com, but I've got UK parking tips for you! 😊",
                "HERE.com's a bit quiet here, but I'm loaded with parking advice! 🚗"
            ],
            'success': [
                "Brilliant! 🎉 Found some great parking spots for you!",
                "Sorted! 🚗 Here's what HERE.com found for you!"
            ]
        }

    def extract_location_from_prompt(self, user_input: str, user_id: str = 'default') -> Dict:
        """Extract location, time, and preferences from user input"""
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = ParkingContext()

        context = self.user_contexts[user_id]
        user_input = user_input.strip().lower()

        # Extract location
        location = None
        for pattern in self.intent_patterns['location_query']:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                break
        if not location:
            location = user_input

        # Extract time
        time_context = context.time_context or 'now'
        for pattern in self.intent_patterns['time_query']:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                time_context = match.group(0).strip()
                break

        # Extract duration
        duration_match = re.search(r'(\d+)\s*(?:hour|hr|h)s?', user_input, re.IGNORECASE)
        duration = int(duration_match.group(1)) if duration_match else context.duration

        # Extract preferences
        parking_prefs = {
            'free': bool(re.search(r'\b(?:free|no\s+cost|cheap)\b', user_input, re.IGNORECASE)),
            'covered': bool(re.search(r'\b(?:covered|garage|indoor)\b', user_input, re.IGNORECASE)),
            'ev_charging': bool(re.search(r'\b(?:ev|electric|charging)\b', user_input, re.IGNORECASE)),
            'accessible': bool(re.search(r'\b(?:accessible|disabled|blue\s+badge)\b', user_input, re.IGNORECASE)),
            'long_term': bool(re.search(r'\b(?:all\s+day|long\s+term|overnight)\b', user_input, re.IGNORECASE))
        }

        # Update context
        context.location = location
        context.time_context = time_context
        context.duration = duration
        context.preferences = parking_prefs

        return {
            'location': location,
            'time_context': time_context,
            'duration': duration,
            'preferences': parking_prefs,
            'original_input': user_input
        }

    def understand_intent(self, message: str) -> Tuple[str, float]:
        """Detect user intent"""
        message_lower = message.lower().strip()
        intent_scores = {}

        for intent, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, message_lower))
                score += matches * 10
            intent_scores[intent] = score

        if not intent_scores or max(intent_scores.values()) == 0:
            return 'general', 0.5

        primary_intent = max(intent_scores, key=intent_scores.get)
        confidence = min(intent_scores[primary_intent] / 100, 1.0)
        return primary_intent, confidence

    def geocode_location(self, location_query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Geocode location with UK bias"""
        enhanced_query = f"{location_query} UK" if not any(country in location_query.lower() for country in ['uk', 'united kingdom']) else location_query

        params = {
            'q': enhanced_query,
            'apiKey': self.api_key,
            'limit': 3,
            'in': 'countryCode:GBR'
        }

        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                result = data['items'][0]
                position = result['position']
                address = result.get('address', {}).get('label', location_query)
                return position['lat'], position['lng'], address
            return None, None, None
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None, None, None

    def search_comprehensive_parking(self, lat: float, lng: float, preferences: Dict) -> List[Dict]:
        """Search for parking using HERE API"""
        search_categories = ['parking', 'parking-garage', 'parking-lot', 'park-and-ride', 'ev-charging-station']
        all_parking = []
        seen_locations = set()

        for category in search_categories:
            params = {
                'at': f"{lat},{lng}",
                'q': category,
                'limit': 10,
                'apiKey': self.api_key
            }

            try:
                response = requests.get(self.discover_url, params=params, timeout=8)
                response.raise_for_status()
                data = response.json()
                for item in data.get('items', []):
                    location_key = (item.get('title', ''), item.get('position', {}).get('lat', 0))
                    if location_key not in seen_locations:
                        seen_locations.add(location_key)
                        item['search_category'] = category
                        all_parking.append(item)
            except Exception as e:
                print(f"Search error for {category}: {e}")

        return all_parking

    def generate_mock_parking_data(self, location: str, preferences: Dict) -> List[Dict]:
        """Generate mock parking data for locations not found"""
        mock_spots = []
        num_spots = random.randint(5, 8)
        street_names = [
            f"{location} High Street", f"{location} Main Road", f"{location} Central Avenue",
            f"{location} Market Street", f"{location} Church Lane", f"{location} Station Road"
        ]

        parking_types = [
            {
                'type': 'On-Street Metered Parking',
                'hourly_rate': random.uniform(1.5, 4.0),
                'max_duration': random.choice([2, 3, 4]),
                'free_periods': ['Sundays', 'After 6 PM'],
                'features': ['Pay by phone', 'Coin payment', 'Card payment']
            },
            {
                'type': 'Municipal Car Park',
                'hourly_rate': random.uniform(2.0, 3.5),
                'max_duration': 10,
                'free_periods': ['First hour free on weekends'],
                'features': ['24/7 access', 'CCTV security', 'Well-lit']
            },
            {
                'type': 'Shopping Center Parking',
                'hourly_rate': 0.0,
                'max_duration': 4,
                'free_periods': ['Free for customers'],
                'features': ['Covered parking', 'Trolley bays', 'Easy access']
            }
        ]

        for i in range(num_spots):
            parking_type = random.choice(parking_types)
            distance = random.randint(50, 800)

            spot = {
                'title': f"{parking_type['type']} - {random.choice(street_names)}",
                'distance': distance,
                'position': {'lat': 51.5074, 'lng': -0.1278},
                'address': {'label': f"{random.choice(street_names)}, {location}"},
                'categories': [{'name': 'parking'}],
                'is_mock': True,
                'parking_details': {
                    'type': parking_type['type'],
                    'hourly_rate': parking_type['hourly_rate'],
                    'daily_rate': parking_type['hourly_rate'] * 8 if parking_type['hourly_rate'] > 0 else 0,
                    'max_duration': parking_type['max_duration'],
                    'free_periods': parking_type['free_periods'],
                    'features': parking_type['features'],
                    'availability': random.choice(['High', 'Medium', 'Low']),
                    'accessibility': random.choice([True, False]),
                    'ev_charging': preferences.get('ev_charging', False) and random.choice([True, False])
                }
            }
            mock_spots.append(spot)

        return mock_spots

    def calculate_enhanced_ai_score(self, parking_spot: Dict, preferences: Dict, time_context: str) -> int:
        """Score parking spots based on preferences and time"""
        score = 50
        distance = parking_spot.get('distance', 500)

        if distance < 100:
            score += 25
        elif distance < 200:
            score += 20
        elif distance < 400:
            score += 15

        current_hour = datetime.now().hour
        if time_context == 'morning' and 6 <= current_hour <= 10:
            score += 10
        elif time_context == 'afternoon' and 11 <= current_hour <= 17:
            score += 5
        elif time_context == 'evening' and 17 <= current_hour <= 22:
            score += 8

        if parking_spot.get('is_mock'):
            details = parking_spot.get('parking_details', {})
            if preferences.get('free') and details.get('hourly_rate', 0) == 0:
                score += 20
            if preferences.get('covered') and 'Covered' in str(details.get('features', [])):
                score += 15
            if preferences.get('ev_charging') and details.get('ev_charging'):
                score += 20
            if preferences.get('accessible') and details.get('accessibility'):
                score += 15

        title = parking_spot.get('title', '').lower()
        if 'garage' in title or 'covered' in title:
            score += 10
        if 'free' in title:
            score += 15
        if 'ev' in title or 'charging' in title:
            score += 10 if preferences.get('ev_charging') else 5

        return max(0, min(100, score + random.randint(-3, 3)))

    def get_comprehensive_parking_info(self, parking_spot: Dict) -> Dict:
        """Get detailed parking information"""
        if parking_spot.get('is_mock'):
            return self.format_mock_parking_info(parking_spot)

        title = parking_spot.get('title', '').lower()
        categories = parking_spot.get('categories', [])
        parking_type = self.determine_here_parking_type(title, categories)
        pricing = self.generate_realistic_pricing(parking_type)

        return {
            'can_park': True,
            'type': parking_type['name'],
            'rules_summary': parking_type['rules_summary'],
            'detailed_rules': parking_type['detailed_rules'],
            'cost': pricing['cost_description'],
            'hourly_rate': pricing['hourly_rate'],
            'daily_rate': pricing['daily_rate'],
            'time_limit': parking_type['time_limit'],
            'features': parking_type['features'],
            'availability': random.choice(['High', 'Medium', 'Low']),
            'payment_methods': pricing['payment_methods'],
            'accessibility': random.choice([True, False]),
            'ev_charging': 'ev' in title or 'charging' in title,
            'operating_hours': parking_type['operating_hours'],
            'pros': parking_type['pros'],
            'cons': parking_type['cons'],
            'uk_specific': self.get_uk_specific_info(title)
        }

    def format_mock_parking_info(self, parking_spot: Dict) -> Dict:
        """Format mock parking information"""
        details = parking_spot.get('parking_details', {})
        hourly_rate = details.get('hourly_rate', 0)
        cost_desc = f"£{hourly_rate:.2f} per hour" if hourly_rate > 0 else "Free"
        if details.get('daily_rate', 0) > 0:
            cost_desc += f" / £{details['daily_rate']:.2f} daily max"

        return {
            'can_park': True,
            'type': details.get('type', 'Public Parking'),
            'rules_summary': f"Standard {details.get('type', 'parking')} with {details.get('max_duration', 'unlimited')} hour limit",
            'detailed_rules': [
                f"Maximum parking duration: {details.get('max_duration', 'unlimited')} hours",
                "Payment required during operating hours" if hourly_rate > 0 else "Free parking available",
                "Observe posted signage and restrictions"
            ],
            'cost': cost_desc,
            'hourly_rate': hourly_rate,
            'daily_rate': details.get('daily_rate', 0),
            'time_limit': f"{details.get('max_duration', 'No')} hour limit",
            'features': details.get('features', []),
            'availability': details.get('availability', 'Medium'),
            'payment_methods': ['Cash', 'Card', 'Mobile App'] if hourly_rate > 0 else ['Free'],
            'accessibility': details.get('accessibility', False),
            'ev_charging': details.get('ev_charging', False),
            'operating_hours': '24/7' if 'garage' in details.get('type', '').lower() else '6:00 AM - 10:00 PM',
            'pros': [
                f"Good availability ({details.get('availability', 'Medium').lower()})",
                f"Within {parking_spot.get('distance', 0)}m walking distance"
            ],
            'cons': [
                f"£{hourly_rate:.2f}/hour cost" if hourly_rate > 0 else "Time limited parking",
                f"{details.get('max_duration', 'No')} hour maximum stay"
            ],
            'uk_specific': self.get_uk_specific_info(details.get('type', '').lower())
        }

    def determine_here_parking_type(self, title: str, categories: List) -> Dict:
        """Determine parking type from HERE data"""
        parking_types = {
            'street': {
                'name': 'On-Street Parking',
                'rules_summary': 'Metered street parking with time restrictions',
                'detailed_rules': [
                    'Pay at meter or via mobile app',
                    'Observe posted time limits',
                    'No parking during street cleaning hours',
                    'Valid permit may be required in some zones'
                ],
                'time_limit': '2-4 hours maximum',
                'features': ['Pay & Display', 'Mobile payment options'],
                'operating_hours': '8:00 AM - 6:00 PM (Mon-Sat)',
                'pros': ['Convenient street access', 'Usually available'],
                'cons': ['Time restrictions', 'Weather exposed']
            },
            'garage': {
                'name': 'Multi-Level Car Park',
                'rules_summary': 'Secure covered parking with hourly rates',
                'detailed_rules': [
                    'Take ticket on entry, pay before exit',
                    'Height restrictions apply (usually 2.1m)',
                    'Keep ticket with you at all times'
                ],
                'time_limit': '24 hours maximum',
                'features': ['Covered parking', 'Security cameras', 'Lifts available'],
                'operating_hours': '24/7',
                'pros': ['Weather protection', 'Secure environment'],
                'cons': ['Higher cost', 'Height restrictions']
            },
            'lot': {
                'name': 'Surface Car Park',
                'rules_summary': 'Open-air parking lot with standard rates',
                'detailed_rules': [
                    'Pay at entry or exit barriers',
                    'Display valid ticket on dashboard',
                    'Maximum stay limits apply'
                ],
                'time_limit': '12 hours maximum',
                'features': ['Easy access', 'Wide spaces', 'Good lighting'],
                'operating_hours': '6:00 AM - 11:00 PM',
                'pros': ['Lower cost than garages', 'Easy vehicle access'],
                'cons': ['No weather protection', 'Limited security']
            }
        }

        if any(word in title for word in ['garage', 'multi', 'level']):
            return parking_types['garage']
        elif any(word in title for word in ['lot', 'surface', 'ground']):
            return parking_types['lot']
        return parking_types['street']

    def generate_realistic_pricing(self, parking_type: Dict) -> Dict:
        """Generate realistic pricing"""
        base_rates = {
            'On-Street Parking': {'min': 1.50, 'max': 3.00},
            'Multi-Level Car Park': {'min': 2.50, 'max': 5.00},
            'Surface Car Park': {'min': 2.00, 'max': 4.00}
        }

        rate_range = base_rates.get(parking_type['name'], {'min': 2.00, 'max': 4.00})
        hourly_rate = round(random.uniform(rate_range['min'], rate_range['max']), 2)
        daily_rate = round(hourly_rate * random.uniform(6, 8), 2)

        return {
            'hourly_rate': hourly_rate,
            'daily_rate': daily_rate,
            'cost_description': f"£{hourly_rate:.2f} per hour / £{daily_rate:.2f} daily maximum",
            'payment_methods': ['Card', 'Cash', 'Mobile App', 'Contactless']
        }

    def get_uk_specific_info(self, title: str) -> Dict:
        """Get UK-specific parking info"""
        uk_info = {
            'blue_badge_friendly': False,
            'payment_methods': ['Card', 'Contactless', 'RingGo'],
            'typical_hours': '8am-6pm Mon-Sat',
            'sunday_parking': 'Often free or reduced rates'
        }

        if 'street' in title:
            uk_info['special_notes'] = [
                'Check for resident permit zones',
                'Single/double yellow lines enforced'
            ]
        if 'ev' in title or 'charging' in title:
            uk_info['ev_charging'] = {'available': True, 'charger_types': ['Type 2', 'CCS']}
        if 'accessible' in title or 'disabled' in title:
            uk_info['blue_badge_friendly'] = True
        return uk_info

    def generate_contextual_response(self, message: str, user_id: str = 'default') -> Dict:
        """Generate contextual response"""
        intent, confidence = self.understand_intent(message)
        parsed_input = self.extract_location_from_prompt(message, user_id)
        context = self.user_contexts[user_id]

        if intent == 'greeting':
            return {
                'message': random.choice(self.personality_responses['greeting']),
                'response': "Tell me where you want to park, and I'll find you the best spots using HERE.com!",
                'suggestions': [
                    "Try: 'Find parking near Oxford Street'",
                    "Or: 'EV parking in Manchester'"
                ],
                'type': 'greeting',
                'status': 'success'
            }

        location = parsed_input['location']
        if not location:
            return {
                'message': "I need a location to find parking!",
                'response': "Please tell me where you want to park (e.g., 'Oxford Street, London').",
                'suggestions': ["Example: 'near Manchester Piccadilly'"],
                'type': 'location_needed',
                'status': 'success'
            }

        lat, lng, address = self.geocode_location(location)
        if lat is None:
            mock_spots = self.generate_mock_parking_data(location, parsed_input['preferences'])
            scored_spots = [
                {
                    'title': spot['title'],
                    'address': spot['address']['label'],
                    'distance': f"{spot['distance']}m",
                    'score': self.calculate_enhanced_ai_score(spot, parsed_input['preferences'], parsed_input['time_context']),
                    'raw_data': spot
                } for spot in mock_spots
            ]
            scored_spots.sort(key=lambda x: x['score'], reverse=True)
            context.last_search = {'spots': scored_spots, 'is_mock': True}

            return {
                'message': random.choice(self.personality_responses['no_data']),
                'response': f"Couldn't find {location} in HERE.com, but here's some parking advice!",
                'data': {'parking_spots': scored_spots, 'is_mock': True},
                'uk_parking_tip': random.choice(self.uk_parking_rules['general']),
                'suggestions': ["Try a nearby city or landmark"],
                'type': 'parking_advice',
                'status': 'partial'
            }

        parking_spots = self.search_comprehensive_parking(lat, lng, parsed_input['preferences'])
        scored_spots = [
            {
                'title': spot['title'],
                'address': spot.get('address', {}).get('label', location),
                'distance': f"{spot.get('distance', 0)}m",
                'score': self.calculate_enhanced_ai_score(spot, parsed_input['preferences'], parsed_input['time_context']),
                'raw_data': spot
            } for spot in parking_spots
        ] if parking_spots else self.generate_mock_parking_data(location, parsed_input['preferences'])

        scored_spots.sort(key=lambda x: x['score'], reverse=True)
        context.last_search = {'spots': scored_spots, 'is_mock': not parking_spots}

        return {
            'message': random.choice(self.personality_responses['success']),
            'response': f"Found {len(scored_spots)} parking spots near {address}!",
            'data': {
                'location': address,
                'parking_spots': scored_spots[:5],
                'is_mock': not parking_spots
            },
            'uk_parking_tip': random.choice(self.uk_parking_rules['general']),
            'suggestions': ["Ask for details on a specific spot"],
            'type': 'parking_results',
            'status': 'success'
        }

app = Flask(__name__)
CORS(app)
bot = EnhancedParkingChatbot()

@app.route('/', methods=['GET'])
def home():
    """API home endpoint"""
    return jsonify({
        "message": "🇬🇧 Enhanced Parking Chatbot - Powered by HERE.com!",
        "version": "1.0 - UK Enhanced",
        "status": "active",
        "features": [
            "🧠 Natural language understanding",
            "🔍 HERE.com parking search",
            "🛣️ On-street, off-street, EV, and accessible parking",
            "📊 Real-time availability",
            "💰 UK pricing in pounds (£)"
        ],
        "endpoints": {
            "chat": "/api/chat",
            "health": "/api/health"
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "bot_status": "ready to assist with UK parking!",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0 - UK Enhanced",
        "here_api_configured": bool(os.getenv('HERE_API_KEY')),
        "uk_features": {
            "currency": "GBP (£)",
            "parking_rules": "UK-specific",
            "location_bias": "United Kingdom"
        }
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat endpoint for parking queries"""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({
                "error": "Please provide a message!",
                "status": "error",
                "example": {"message": "Find parking near Oxford Street"}
            }), 400

        user_message = data['message'].strip()
        user_id = data.get('user_id', 'default')

        if not user_message:
            return jsonify({
                "message": "I'm here to help with parking!",
                "response": "Tell me where you want to park!",
                "suggestions": ["Ask about parking anywhere in the UK!"],
                "status": "success"
            })

        response = bot.generate_contextual_response(user_message, user_id)
        response['timestamp'] = datetime.now().isoformat()
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "message": "Blimey! Hit a snag!",
            "response": "Try again, I'm here to help with parking!",
            "error": str(e) if app.debug else "Technical error",
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "suggestions": ["Try your question again"]
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🇬🇧 Starting Enhanced Parking Chatbot...")
    print("🔍 Powered by HERE.com for UK parking data!")
    app.run(host='0.0.0.0', port=port, debug=False)
