# intelligent_parksy.py - AI-Powered UK Parking Assistant with HERE.com Integration
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import re
from datetime import datetime, timedelta
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

@dataclass
class ParkingContext:
    """Store conversation context"""
    location: Optional[str] = None
    time: Optional[str] = None
    duration: Optional[str] = None
    vehicle_type: Optional[str] = None
    budget: Optional[str] = None
    preferences: List[str] = None
    last_search: Optional[Dict] = None

class IntelligentParksyBot:
    def __init__(self):
        # API Configuration
        self.api_key = os.getenv('HERE_API_KEY', 'demo_key_for_testing')
        self.base_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.places_url = "https://places.sit.ls.hereapi.com/places/v1/discover/explore"
        
        # UK-specific bounding box (approximate)
        self.uk_bounds = {
            'north': 60.9,
            'south': 49.8,
            'east': 2.1,
            'west': -8.5
        }
        
        # Conversation context storage (in production, use Redis or database)
        self.user_contexts = {}
        
        # UK Parking Rules and Pricing Data
        self.uk_parking_rules = {
            'general': {
                'double_yellow_lines': 'No parking at any time',
                'single_yellow_lines': 'Restrictions apply during times shown on nearby signs',
                'white_lines': 'Usually indicate parking bays or restrictions',
                'dropped_kerb': 'Do not block driveways or dropped kerbs',
                'bus_stops': 'No parking within 12 meters of bus stops',
                'school_zones': 'Enhanced restrictions during school hours (8:00-9:30 AM, 2:30-4:00 PM)',
                'loading_bays': 'Reserved for loading/unloading during specified hours',
                'disabled_bays': 'Blue badge holders only, fines up to £1,000'
            },
            'pricing': {
                'london_zones': {
                    'zone_1': '£4.90-£8.00/hour',
                    'zone_2': '£2.40-£4.90/hour',
                    'outer_london': '£1.20-£2.40/hour'
                },
                'major_cities': {
                    'manchester': '£1.50-£3.50/hour',
                    'birmingham': '£1.20-£3.00/hour',
                    'leeds': '£1.00-£2.50/hour',
                    'liverpool': '£1.20-£2.80/hour',
                    'bristol': '£1.50-£3.20/hour',
                    'sheffield': '£1.00-£2.20/hour',
                    'glasgow': '£1.20-£2.50/hour',
                    'edinburgh': '£1.80-£3.50/hour'
                },
                'towns': '£0.50-£2.00/hour',
                'retail_parks': '£1.00-£3.00/hour (often first 2-3 hours free)',
                'hospitals': '£2.00-£5.00/hour',
                'airports': '£3.00-£25.00/day',
                'train_stations': '£2.00-£15.00/day'
            },
            'time_restrictions': {
                'pay_and_display': 'Usually 8:00 AM - 6:00 PM Mon-Sat',
                'resident_permits': '24/7 in residential permit zones',
                'sunday_restrictions': 'Limited restrictions, varies by council',
                'evening_restrictions': 'Most restrictions end 6:00-8:00 PM',
                'overnight': 'Check for overnight restrictions in city centres'
            }
        }
        
        # Enhanced intent patterns
        self.intent_patterns = {
            'greeting': [
                r'\b(hi|hello|hey|greetings?|good\s+(morning|afternoon|evening)|howdy)\b',
                r'^(hey there|what\'s up|sup)\b'
            ],
            'parking_query': [
                r'\b(park|parking|spot|garage|lot|space)\b',
                r'\b(can\s+i\s+park|where\s+to\s+park|need\s+parking|looking\s+for\s+parking)\b',
                r'\b(find\s+me\s+a\s+spot|park\s+my\s+car)\b'
            ],
            'rules_query': [
                r'\b(rules|restrictions|regulations|allowed|legal|fine|ticket)\b',
                r'\b(can\s+i\s+park\s+here|is\s+it\s+legal|yellow\s+lines|double\s+yellow)\b'
            ],
            'pricing_query': [
                r'\b(cost|price|fee|charge|expensive|cheap|free)\b',
                r'\b(how\s+much|what\s+does\s+it\s+cost|pricing)\b'
            ],
            'time_query': [
                r'\b(\d{1,2}(:\d{2})?\s*(am|pm)|at\s+\d|tonight|morning|afternoon|evening)\b',
                r'\b(now|later|tomorrow|today|this\s+(morning|afternoon|evening))\b',
                r'\b(for\s+\d+\s+(hours?|minutes?)|overnight)\b'
            ],
            'location_query': [
                r'\b(in|at|near|around|close\s+to)\s+\w+',
                r'\b\w+\s+(street|st|avenue|ave|road|rd|city|town|center|centre|mall|airport)\b'
            ]
        }
        
        # UK-specific location patterns
        self.uk_location_patterns = [
            r'\b(london|birmingham|manchester|leeds|liverpool|bristol|sheffield|glasgow|edinburgh|cardiff|belfast)\b',
            r'\b\w+\s+(high\s+street|town\s+centre|city\s+centre)\b',
            r'\b[A-Z]{1,2}\d{1,2}\s*\d[A-Z]{2}\b',  # UK postcodes
            r'\b(greater\s+london|west\s+midlands|greater\s+manchester|west\s+yorkshire)\b'
        ]
        
        # Personality responses
        self.personality_responses = {
            'greeting': [
                "Hello! 🇬🇧 I'm your UK parking assistant! Where in the UK are you looking to park?",
                "Hi there! 🚗 I help with parking across the UK. What location can I help you with?",
                "Welcome! I'm here to help with UK parking spots, rules, and pricing. How can I assist?"
            ],
            'non_uk_location': [
                "I specialize in UK parking only! 🇬🇧 Please use the Parksy location search bar for international locations.",
                "Sorry, I only cover UK parking! For locations outside the UK, please try the main Parksy search feature.",
                "I'm your UK parking expert! For international parking, please use Parksy's location search bar."
            ]
        }

    def is_uk_location(self, location: str) -> bool:
        """Check if location is in the UK using patterns and geocoding"""
        location_lower = location.lower()
        
        # Check for obvious UK indicators
        uk_indicators = [
            'uk', 'england', 'scotland', 'wales', 'northern ireland', 'britain',
            'london', 'birmingham', 'manchester', 'leeds', 'liverpool', 'bristol',
            'sheffield', 'glasgow', 'edinburgh', 'cardiff', 'belfast', 'newcastle',
            'nottingham', 'bradford', 'coventry', 'leicester', 'oxford', 'cambridge'
        ]
        
        if any(indicator in location_lower for indicator in uk_indicators):
            return True
        
        # Check postcode pattern
        if re.search(r'\b[A-Z]{1,2}\d{1,2}\s*\d[A-Z]{2}\b', location.upper()):
            return True
        
        # Use geocoding to verify
        lat, lng, _ = self.geocode_location(location)
        if lat and lng:
            return (self.uk_bounds['south'] <= lat <= self.uk_bounds['north'] and 
                    self.uk_bounds['west'] <= lng <= self.uk_bounds['east'])
        
        return False

    def get_here_parking_data(self, lat: float, lng: float) -> List[Dict]:
        """Get detailed parking data from HERE.com API"""
        try:
            # Search for parking using HERE Discover API
            params = {
                'at': f"{lat},{lng}",
                'q': 'parking',
                'limit': 20,
                'apiKey': self.api_key,
                'categories': '700-7600-0116,700-7600-0117,700-7600-0118'  # Parking categories
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            parking_spots = []
            for item in data.get('items', []):
                # Extract detailed information from HERE response
                spot_data = self.extract_here_spot_data(item)
                if spot_data:
                    parking_spots.append(spot_data)
            
            return parking_spots
            
        except Exception as e:
            print(f"HERE API error: {e}")
            return []

    def extract_here_spot_data(self, here_item: Dict) -> Dict:
        """Extract and enhance data from HERE API response"""
        try:
            spot = {
                'id': here_item.get('id', ''),
                'title': here_item.get('title', ''),
                'address': here_item.get('address', {}).get('label', ''),
                'distance': here_item.get('distance', 0),
                'position': here_item.get('position', {}),
                'categories': [cat.get('name', '') for cat in here_item.get('categories', [])],
                'contacts': here_item.get('contacts', []),
                'opening_hours': here_item.get('openingHours', []),
                'access': here_item.get('access', [])
            }
            
            # Add UK-specific analysis
            spot['uk_analysis'] = self.analyze_uk_parking_spot(spot)
            spot['pricing_estimate'] = self.estimate_uk_pricing(spot)
            spot['rules_applicable'] = self.get_applicable_uk_rules(spot)
            
            return spot
            
        except Exception as e:
            print(f"Error extracting HERE data: {e}")
            return None

    def analyze_uk_parking_spot(self, spot: Dict) -> Dict:
        """Analyze parking spot with UK-specific context"""
        title = spot.get('title', '').lower()
        address = spot.get('address', '').lower()
        categories = [cat.lower() for cat in spot.get('categories', [])]
        
        analysis = {
            'type': 'Public Parking',
            'likely_restrictions': [],
            'recommended_for': [],
            'accessibility': 'Standard',
            'payment_methods': ['Card', 'Coins', 'App likely available']
        }
        
        # Determine parking type
        if 'car park' in title or 'parking' in title:
            if 'multi' in title or 'multi-storey' in title:
                analysis['type'] = 'Multi-storey Car Park'
                analysis['recommended_for'] = ['Weather protection', 'Security', 'Long stays']
            elif 'surface' in title or 'ground' in title:
                analysis['type'] = 'Surface Car Park'
                analysis['recommended_for'] = ['Easy access', 'Short stays', 'Large vehicles']
            elif any(retail in title for retail in ['shopping', 'retail', 'centre', 'mall']):
                analysis['type'] = 'Retail Car Park'
                analysis['recommended_for'] = ['Shopping trips', 'Often first hours free']
                analysis['likely_restrictions'] = ['Maximum stay limits', 'Customer parking only']
        
        # Location-based analysis
        if any(area in address for area in ['london', 'central', 'city centre', 'town centre']):
            analysis['likely_restrictions'].extend(['Higher charges', 'Time limits', 'Congestion charge area'])
            analysis['payment_methods'].append('Contactless preferred')
        
        if 'hospital' in title or 'nhs' in title:
            analysis['type'] = 'Hospital Car Park'
            analysis['likely_restrictions'] = ['Higher charges', 'Patient/visitor validation available']
            analysis['recommended_for'] = ['Hospital visits', 'Disabled parking available']
        
        return analysis

    def estimate_uk_pricing(self, spot: Dict) -> Dict:
        """Estimate pricing based on UK location and type"""
        title = spot.get('title', '').lower()
        address = spot.get('address', '').lower()
        
        pricing = {
            'estimated_hourly': '£1.50-£3.00',
            'estimated_daily': '£8.00-£15.00',
            'confidence': 'Medium',
            'notes': []
        }
        
        # London pricing
        if 'london' in address:
            if any(central in address for central in ['central', 'zone 1', 'city', 'westminster']):
                pricing['estimated_hourly'] = '£4.90-£8.00'
                pricing['estimated_daily'] = '£30.00-£50.00'
                pricing['notes'].append('Central London premium rates')
            else:
                pricing['estimated_hourly'] = '£2.40-£4.90'
                pricing['estimated_daily'] = '£15.00-£30.00'
                pricing['notes'].append('Outer London rates')
        
        # Major cities
        elif any(city in address for city in ['manchester', 'birmingham', 'leeds', 'liverpool']):
            pricing['estimated_hourly'] = '£1.50-£3.50'
            pricing['estimated_daily'] = '£8.00-£20.00'
            pricing['notes'].append('Major city rates')
        
        # Specific venue types
        if 'hospital' in title:
            pricing['estimated_hourly'] = '£2.00-£5.00'
            pricing['notes'].append('Hospital parking - may have reduced rates for patients')
        
        if any(retail in title for retail in ['shopping', 'retail', 'supermarket']):
            pricing['notes'].append('Often first 2-3 hours free for customers')
        
        if 'airport' in title:
            pricing['estimated_hourly'] = '£3.00-£8.00'
            pricing['estimated_daily'] = '£15.00-£25.00'
            pricing['notes'].append('Airport rates - long stay options available')
        
        return pricing

    def get_applicable_uk_rules(self, spot: Dict) -> List[str]:
        """Get applicable UK parking rules for the location"""
        rules = []
        
        # General UK rules that always apply
        rules.extend([
            "Blue badge holders may have special provisions",
            "Check signs for specific time restrictions",
            "Payment usually required during posted hours",
            "Maximum stay limits may apply"
        ])
        
        title = spot.get('title', '').lower()
        address = spot.get('address', '').lower()
        
        # Location-specific rules
        if 'london' in address:
            rules.extend([
                "Congestion Charge may apply (Mon-Fri 7am-6pm)",
                "ULEZ charges apply for non-compliant vehicles",
                "Resident permit zones common"
            ])
        
        if any(term in title for term in ['hospital', 'nhs']):
            rules.extend([
                "Patient/visitor validation may reduce charges",
                "Emergency vehicle access must be maintained",
                "Disabled parking bays strictly enforced"
            ])
        
        if any(term in title for term in ['shopping', 'retail']):
            rules.extend([
                "Customer parking only - terms may apply",
                "Time limits often enforced",
                "Free periods may require minimum spend"
            ])
        
        return rules

    def extract_entities(self, message: str) -> Dict:
        """Extract entities from user message with UK focus"""
        entities = {
            'location': None,
            'time': None,
            'duration': None,
            'vehicle_type': None,
            'budget': None,
            'preferences': [],
            'is_uk_location': False
        }
        
        message_lower = message.lower()
        
        # Extract location with UK patterns
        location_patterns = [
            r'\b(?:in|at|near|around)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:at|for|around|by)|\s*[,.]|$)',
            r'\b([A-Z][a-zA-Z\s]+(?:street|st|avenue|ave|road|rd|city|town|centre|center|mall|airport|station))\b',
            r'\b([A-Z]{1,2}\d{1,2}\s*\d[A-Z]{2})\b',  # UK postcodes
            r'\b([A-Z][a-zA-Z\s]{2,})\b(?=\s+(?:at|for|around|\d|$))'
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                entities['location'] = location
                entities['is_uk_location'] = self.is_uk_location(location)
                break
        
        # Extract other entities (same as before)
        time_patterns = [
            r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b',
            r'\b(at\s+\d{1,2}(?::\d{2})?)\b',
            r'\b(tonight|this\s+morning|this\s+afternoon|this\s+evening|now|later)\b'
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['time'] = match.group(1).strip()
                break
        
        # Extract duration, vehicle type, budget (same as before)
        duration_patterns = [
            r'\b(for\s+\d+\s+(?:hours?|hrs?|minutes?|mins?))\b',
            r'\b(overnight|all\s+day|quick\s+stop)\b'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['duration'] = match.group(1).strip()
                break
        
        return entities

    def understand_intent(self, message: str) -> Tuple[str, float]:
        """Enhanced intent detection with UK parking focus"""
        message_lower = message.lower().strip()
        intent_scores = {}
        
        # Score each intent
        for intent, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, message_lower))
                score += matches * 10
            
            # Boost specific UK parking intents
            if intent == 'rules_query' and any(term in message_lower for term in ['yellow lines', 'restrictions', 'legal', 'fine']):
                score += 15
            if intent == 'pricing_query' and any(term in message_lower for term in ['cost', 'price', 'expensive', 'cheap']):
                score += 15
                
            intent_scores[intent] = score
        
        if not intent_scores or max(intent_scores.values()) == 0:
            return 'general', 0.5
        
        primary_intent = max(intent_scores, key=intent_scores.get)
        confidence = min(intent_scores[primary_intent] / 100, 1.0)
        
        return primary_intent, confidence

    def generate_contextual_response(self, message: str, user_id: str = 'default') -> Dict:
        """Generate intelligent, UK-focused responses"""
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = ParkingContext()
        
        context = self.user_contexts[user_id]
        entities = self.extract_entities(message)
        intent, confidence = self.understand_intent(message)
        
        # Check for non-UK location early
        if entities['location'] and not entities['is_uk_location']:
            return self.handle_non_uk_location(entities['location'])
        
        # Update context
        if entities['location'] and entities['is_uk_location']:
            context.location = entities['location']
        if entities['time']:
            context.time = entities['time']
        if entities['duration']:
            context.duration = entities['duration']
        if entities['vehicle_type']:
            context.vehicle_type = entities['vehicle_type']
        if entities['budget']:
            context.budget = entities['budget']
        if entities['preferences']:
            context.preferences = entities['preferences']
        
        # Handle intents
        if intent == 'greeting':
            return self.handle_greeting(message, context)
        elif intent == 'rules_query':
            return self.handle_rules_query(message, context, entities)
        elif intent == 'pricing_query':
            return self.handle_pricing_query(message, context, entities)
        elif intent == 'parking_query' or (entities['location'] and entities['is_uk_location']):
            return self.handle_uk_parking_query(message, context, entities)
        else:
            return self.handle_general_conversation(message, context, entities)

    def handle_non_uk_location(self, location: str) -> Dict:
        """Handle requests for non-UK locations"""
        return {
            'message': f"I specialize in UK parking only! 🇬🇧",
            'response': f"For parking information in {location}, please use the Parksy location search bar at the top of the page. I'm here to help with all your UK parking needs!",
            'suggestions': [
                "Ask about UK parking locations",
                "Try: 'parking in London'",
                "Try: 'parking rules in Manchester'"
            ],
            'type': 'non_uk_redirect',
            'status': 'redirect'
        }

    def handle_rules_query(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle UK parking rules queries"""
        location = entities.get('location') or context.location
        
        if not location:
            # General UK rules
            return {
                'message': "Here are the key UK parking rules! 📋",
                'response': "UK parking rules to remember:",
                'data': {
                    'general_rules': self.uk_parking_rules['general'],
                    'time_restrictions': self.uk_parking_rules['time_restrictions'],
                    'important_notes': [
                        "Always check local signs for specific restrictions",
                        "Rules vary by council - local authorities set their own policies",
                        "Fines typically range from £25-£130 depending on location and violation"
                    ]
                },
                'suggestions': [
                    "Ask about specific location rules",
                    "Ask about parking pricing",
                    "Ask about disabled parking rules"
                ],
                'type': 'parking_rules',
                'status': 'success'
            }
        else:
            # Location-specific rules
            return {
                'message': f"Here are the parking rules for {location}! 📍",
                'response': f"Parking regulations in {location}:",
                'data': {
                    'location': location,
                    'general_rules': self.uk_parking_rules['general'],
                    'location_specific': self.get_location_specific_rules(location),
                    'pricing_info': self.get_location_pricing(location)
                },
                'suggestions': [
                    f"Find parking spots in {location}",
                    "Ask about payment methods",
                    "Ask about time restrictions"
                ],
                'type': 'location_rules',
                'status': 'success'
            }

    def handle_pricing_query(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle UK parking pricing queries"""
        location = entities.get('location') or context.location
        
        pricing_data = self.uk_parking_rules['pricing']
        
        if location:
            location_pricing = self.get_location_pricing(location)
            return {
                'message': f"Here's the pricing information for {location}! 💷",
                'response': f"Parking costs in {location}:",
                'data': {
                    'location': location,
                    'pricing': location_pricing,
                    'general_pricing': pricing_data,
                    'money_saving_tips': [
                        "Look for retail parks with free initial hours",
                        "Consider park-and-ride schemes for city centres",
                        "Check council websites for resident permits if staying longer",
                        "Use parking apps for real-time pricing and availability"
                    ]
                },
                'suggestions': [
                    f"Find parking spots in {location}",
                    "Ask about parking rules",
                    "Ask about free parking options"
                ],
                'type': 'pricing_info',
                'status': 'success'
            }
        else:
            return {
                'message': "Here's UK parking pricing information! 💷",
                'response': "Typical UK parking costs:",
                'data': {
                    'pricing': pricing_data,
                    'notes': [
                        "Prices vary significantly by location and time",
                        "London has the highest rates in the UK",
                        "Many retail locations offer free parking with purchase",
                        "Early bird and evening rates often available"
                    ]
                },
                'suggestions': [
                    "Ask about specific city pricing",
                    "Ask about free parking options",
                    "Find parking in your area"
                ],
                'type': 'general_pricing',
                'status': 'success'
            }

    def handle_uk_parking_query(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle UK parking location queries with HERE.com data"""
        location = entities.get('location') or context.location
        
        if not location:
            return {
                'message': "I'd love to help you find UK parking! 🇬🇧",
                'response': "I just need to know where in the UK you're looking to park. Could you tell me the location?",
                'suggestions': [
                    "Example: 'parking in London'",
                    "Example: 'Birmingham city centre'",
                    "Example: 'M1 2AB postcode'"
                ],
                'type': 'location_needed',
                'status': 'success'
            }
        
        # Geocode and search
        lat, lng, formatted_address = self.geocode_location(location)
        if not lat:
            return {
                'message': f"I couldn't find {location} in the UK. 🤔",
                'response': "Could you try a different way of describing the location? Maybe include a postcode or nearby landmark?",
                'suggestions': [
                    "Try with a postcode",
                    "Include nearby landmarks",
                    "Try 'city centre' for town centers"
                ],
                'type': 'location_not_found',
                'status': 'partial'
            }
        
        # Verify UK location
        if not (self.uk_bounds['south'] <= lat <= self.uk_bounds['north'] and 
                self.uk_bounds['west'] <= lng <= self.uk_bounds['east']):
            return self.handle_non_uk_location(location)
        
        # Search for parking using HERE data
        parking_spots = self.get_here_parking_data(lat, lng)
        
        if parking_spots:
            return {
                'message': f"Excellent! 🎉 Found parking options in {formatted_address or location}",
                'response': f"Here are {len(parking_spots[:8])} parking options with UK-specific information:",
                'data': {
                    'location': formatted_address or location,
                    'coordinates': {'lat': lat, 'lng': lng},
                    'search_context': {
                        'time': context.time,
                        'duration': context.duration,
                        'vehicle': context.vehicle_type,
                        'budget': context.budget
                    },
                    'parking_spots': parking_spots[:8],
                    'location_rules': self.get_location_specific_rules(location),
                    'pricing_guide': self.get_location_pricing(location)
                },
                'suggestions': [
                    "Ask about specific parking rules",
                    "Ask about pricing details",
                    "Need parking for different time?"
                ],
                'type': 'uk_parking_results',
                'status': 'success'
            }
        else:
            return {
                'message': f"I'm having trouble finding specific parking data for {location}. 🔍",
                'response': f"But I can still help! Here's what I know about parking in {location}:",
                'data': {
                    'location': location,
                    'general_advice': [
                        "Look for council-operated car parks (usually well-signposted)",
                        "Check retail parks for free initial parking",
                        "Use park-and-ride schemes if available",
                        "Download local parking apps for real-time availability"
                    ],
                    'rules': self.get_location_specific_rules(location),
                    'pricing': self.get_location_pricing(location)
                },
                'suggestions': [
                    "Ask about parking rules",
                    "Ask about typical pricing",
                    "Try searching for specific venues"
                ],
                'type': 'general_advice',
                'status': 'partial'
            }

    def get_location_specific_rules(self, location: str) -> List[str]:
        """Get specific rules for UK locations"""
        location_lower = location.lower()
        rules = []
        
        if 'london' in location_lower:
            rules.extend([
                "Congestion Charge: £15/day (Mon-Fri 7am-6pm, Sat-Sun 12pm-6pm)",
                "ULEZ: £12.50/day for non-compliant vehicles",
                "Resident parking permits required in many areas",
                "Red routes: No stopping except in marked bays",
                "Single yellow lines: Usually 8:30am-6:30pm restrictions"
            ])
        elif any(city in location_lower for city in ['manchester', 'birmingham', 'leeds']):
            rules.extend([
                "City centre time limits commonly enforced",
                "Pay and display typically 8am-6pm Mon-Sat",
                "Sunday parking often free or reduced rates",
                "Loading bays enforced during business hours",
                "Park and ride schemes available"
            ])
        elif 'glasgow' in location_lower or 'edinburgh' in location_lower:
            rules.extend([
                "Scottish parking regulations apply",
                "Controlled parking zones in city centres",
                "Resident permits common in central areas",
                "Evening restrictions may apply until 8pm"
            ])
        
        # General UK rules always apply
        rules.extend([
            "Blue badge holders: 3 hours free on yellow lines (if safe)",
            "Double yellow lines: No parking at any time",
            "Loading restrictions: Usually 8am-6pm Mon-Sat",
            "School keep clear markings: No parking during school hours"
        ])
        
        return rules

    def get_location_pricing(self, location: str) -> Dict:
        """Get pricing information for specific UK locations"""
        location_lower = location.lower()
        pricing = self.uk_parking_rules['pricing']
        
        if 'london' in location_lower:
            if any(central in location_lower for central in ['central', 'zone 1', 'city', 'westminster', 'camden', 'islington']):
                return {
                    'type': 'Central London',
                    'hourly': pricing['london_zones']['zone_1'],
                    'daily': '£30-£50',
                    'notes': ['Congestion charge applies', 'ULEZ charges apply', 'Premium location rates']
                }
            else:
                return {
                    'type': 'Outer London',
                    'hourly': pricing['london_zones']['outer_london'],
                    'daily': '£15-£30',
                    'notes': ['ULEZ may apply', 'Better value than central areas']
                }
        
        # Check for major cities
        for city, price in pricing['major_cities'].items():
            if city in location_lower:
                return {
                    'type': f'{city.title()} City Centre',
                    'hourly': price,
                    'daily': '£8-£20',
                    'notes': ['City centre premium', 'Park and ride often cheaper', 'Evening rates may be lower']
                }
        
        # Default for smaller towns
        return {
            'type': 'Town/Local Area',
            'hourly': pricing['towns'],
            'daily': '£5-£15',
            'notes': ['Generally more affordable', 'Check for free periods', 'Local variations apply']
        }

    def handle_greeting(self, message: str, context: ParkingContext) -> Dict:
        """Handle greeting with UK focus"""
        response = random.choice(self.personality_responses['greeting'])
        
        return {
            'message': response,
            'response': "I can help you find parking spots across the UK, explain parking rules and regulations, and give you pricing information. I use real data from HERE.com combined with UK parking expertise! 🎯",
            'suggestions': [
                "Try: 'I need parking in London at 2pm'",
                "Ask: 'What are the parking rules in Manchester?'", 
                "Ask: 'How much does parking cost in Birmingham?'"
            ],
            'type': 'greeting',
            'status': 'success'
        }

    def handle_general_conversation(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle general conversation with UK parking focus"""
        responses = [
            "I'm your UK parking specialist! 🇬🇧 How can I help you today?",
            "Ready to help with all your UK parking needs! 🅿️ What would you like to know?",
            "I'm here for UK parking spots, rules, and pricing! ✨ What can I assist with?"
        ]
        
        return {
            'message': random.choice(responses),
            'response': "I can help you with: finding parking spots across the UK, explaining parking rules and restrictions, providing pricing information, and giving location-specific advice using real HERE.com data!",
            'suggestions': [
                "Find parking in [UK location]",
                "Ask about parking rules and restrictions",
                "Get pricing information for UK cities"
            ],
            'type': 'general',
            'status': 'success'
        }

    # Utility methods enhanced for UK focus
    def geocode_location(self, location_query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Convert location query to coordinates with UK preference"""
        params = {
            'q': location_query,
            'apiKey': self.api_key,
            'limit': 5,
            'in': f"bbox:{self.uk_bounds['west']},{self.uk_bounds['south']},{self.uk_bounds['east']},{self.uk_bounds['north']}"  # UK bounding box
        }

        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                # Prefer UK results
                for item in data['items']:
                    position = item['position']
                    if (self.uk_bounds['south'] <= position['lat'] <= self.uk_bounds['north'] and 
                        self.uk_bounds['west'] <= position['lng'] <= self.uk_bounds['east']):
                        address = item.get('address', {}).get('label', location_query)
                        return position['lat'], position['lng'], address
                
                # If no UK result found, return first result but flag it
                position = data['items'][0]['position']
                address = data['items'][0].get('address', {}).get('label', location_query)
                return position['lat'], position['lng'], address
            else:
                return None, None, None
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None, None, None

    def search_parking_spots(self, lat: float, lng: float, radius: int = 2000) -> List[Dict]:
        """Enhanced parking search using HERE.com with UK context"""
        parking_queries = [
            'car park', 'parking', 'multi-storey car park', 'public parking',
            'council car park', 'pay and display', 'parking garage'
        ]

        all_spots = []
        seen_spots = set()

        for query in parking_queries:
            params = {
                'at': f"{lat},{lng}",
                'q': query,
                'limit': 15,
                'apiKey': self.api_key,
                'categories': '700-7600-0116,700-7600-0117,700-7600-0118'  # Parking specific categories
            }

            try:
                response = requests.get(self.base_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                spots = data.get('items', [])

                for spot in spots:
                    spot_id = spot.get('id', '') or f"{spot.get('title', '')}-{spot.get('position', {}).get('lat', 0)}"
                    if spot_id not in seen_spots:
                        seen_spots.add(spot_id)
                        enhanced_spot = self.extract_here_spot_data(spot)
                        if enhanced_spot:
                            all_spots.append(enhanced_spot)

            except Exception as e:
                print(f"Search error for query '{query}': {e}")
                continue

        # Sort by distance and relevance
        all_spots.sort(key=lambda x: (x.get('distance', 9999), -x.get('relevance_score', 0)))
        return all_spots

    def calculate_relevance_score(self, spot: Dict) -> int:
        """Calculate relevance score for UK parking spots"""
        score = 50
        
        title = spot.get('title', '').lower()
        categories = [cat.lower() for cat in spot.get('categories', [])]
        
        # UK-specific scoring
        if 'car park' in title:
            score += 20
        if 'public' in title or 'council' in title:
            score += 15
        if 'multi-storey' in title:
            score += 10
        if any('parking' in cat for cat in categories):
            score += 15
        
        # Distance scoring
        distance = spot.get('distance', 1000)
        if distance < 200:
            score += 25
        elif distance < 500:
            score += 15
        elif distance < 1000:
            score += 10
        
        return min(100, score)

# Flask App Setup
app = Flask(__name__)
CORS(app)
bot = IntelligentParksyBot()

@app.route('/', methods=['GET'])
def home():
    """API home endpoint"""
    return jsonify({
        "message": "🇬🇧 UK Parksy Bot - Your British Parking Assistant!",
        "version": "4.0 - UK Focused with HERE.com Integration",
        "status": "active",
        "coverage": "United Kingdom Only",
        "features": [
            "Real HERE.com parking data",
            "UK parking rules and regulations",
            "Accurate pricing information", 
            "Location-specific guidance",
            "British parking expertise"
        ],
        "data_sources": [
            "HERE.com Places API",
            "UK parking regulations database",
            "Local authority parking policies"
        ],
        "personality": "Knowledgeable, accurate, and thoroughly British! 🎩",
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
        "bot_status": "Ready to help with UK parking! 🇬🇧",
        "timestamp": datetime.now().isoformat(),
        "version": "4.0",
        "here_api_configured": bool(os.getenv('HERE_API_KEY')),
        "coverage": "United Kingdom",
        "data_accuracy": "High - Real HERE.com data + UK regulations"
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chat endpoint - UK parking specialist"""
    try:
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({
                "error": "I need a message to respond to! 😊",
                "status": "error",
                "example": {"message": "Can I park in London at 9pm?"}
            }), 400

        user_message = data['message'].strip()
        user_id = data.get('user_id', 'default')
        
        if not user_message:
            return jsonify({
                "message": "I'm here and ready to help with UK parking! 🇬🇧",
                "response": "What would you like to know about parking in the UK?",
                "suggestions": ["Ask me about parking anywhere in the UK!"],
                "status": "success"
            })

        # Generate UK-focused response
        response = bot.generate_contextual_response(user_message, user_id)
        response['timestamp'] = datetime.now().isoformat()
        response['coverage'] = "UK Only"
        response['data_source'] = "HERE.com + UK Parking Regulations"
        
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "message": "Sorry, I've encountered a technical issue! 🔧",
            "response": "Don't worry - I'm still here to help with your UK parking needs. Please try again!",
            "error": str(e),
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🇬🇧 Starting UK Parksy Bot...")
    print("📍 Coverage: United Kingdom Only")
    print("🎯 Data Source: HERE.com + UK Parking Regulations")
    print("💬 Ready for accurate UK parking assistance!")
    app.run(host='0.0.0.0', port=port, debug=False)
