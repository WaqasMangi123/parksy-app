# intelligent_parksy.py - AI-Powered UK Parking Assistant with HERE.com Integration
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import re
from datetime import datetime, timedelta
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ParkingContext:
    """Store conversation context"""
    location: Optional[str] = None
    time: Optional[str] = None
    duration: Optional[str] = None
    vehicle_type: Optional[str] = None
    budget: Optional[str] = None
    preferences: List[str] = field(default_factory=list)
    last_search: Optional[Dict] = None

class IntelligentParksyBot:
    def __init__(self):
        # API Configuration with fallback
        self.api_key = os.getenv('HERE_API_KEY', 'demo_key_for_testing')
        self.base_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        
        # Request timeout settings
        self.timeout = 10
        self.max_retries = 2
        
        # Check if API key is valid
        self.api_available = self.api_key != 'demo_key_for_testing' and self.api_key
        
        if not self.api_available:
            logger.warning("HERE API key not found. Running in demo mode.")
        
        # UK-specific bounding box (approximate)
        self.uk_bounds = {
            'north': 60.9,
            'south': 49.8,
            'east': 2.1,
            'west': -8.5
        }
        
        # Conversation context storage
        self.user_contexts = {}
        
        # Mock data for demo mode
        self.demo_parking_spots = [
            {
                'id': 'demo_1',
                'title': 'City Centre Car Park',
                'address': 'High Street, City Centre',
                'distance': 150,
                'position': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Public Parking'],
                'uk_analysis': {
                    'type': 'Multi-storey Car Park',
                    'likely_restrictions': ['Higher charges', 'Time limits'],
                    'recommended_for': ['Weather protection', 'Security'],
                    'accessibility': 'Standard',
                    'payment_methods': ['Card', 'Coins', 'App']
                },
                'pricing_estimate': {
                    'estimated_hourly': '£2.50-£4.00',
                    'estimated_daily': '£15.00-£25.00',
                    'confidence': 'High',
                    'notes': ['City centre rates', 'Evening discounts available']
                }
            },
            {
                'id': 'demo_2', 
                'title': 'Shopping Centre Car Park',
                'address': 'Retail Park, Town Centre',
                'distance': 300,
                'position': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Retail Parking'],
                'uk_analysis': {
                    'type': 'Retail Car Park',
                    'likely_restrictions': ['Customer parking only', 'Maximum stay limits'],
                    'recommended_for': ['Shopping trips', 'First 3 hours free'],
                    'accessibility': 'Disabled spaces available',
                    'payment_methods': ['Card', 'Contactless', 'App']
                },
                'pricing_estimate': {
                    'estimated_hourly': 'Free for 3hrs then £1.50/hr',
                    'estimated_daily': '£8.00',
                    'confidence': 'High',
                    'notes': ['Customer validation available', 'Free with purchase over £10']
                }
            }
        ]
        
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

    def safe_api_request(self, url: str, params: Dict, timeout: int = None) -> Optional[Dict]:
        """Make a safe API request with error handling and retries"""
        if not self.api_available:
            logger.info("API not available, using demo mode")
            return None
            
        timeout = timeout or self.timeout
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Making API request to {url} (attempt {attempt + 1})")
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout on attempt {attempt + 1}")
                if attempt == self.max_retries:
                    logger.error("All retry attempts failed due to timeout")
                    return None
                    
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error on attempt {attempt + 1}")
                if attempt == self.max_retries:
                    logger.error("All retry attempts failed due to connection error")
                    return None
                    
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error: {e}")
                return None
                
            except Exception as e:
                logger.error(f"Unexpected error in API request: {e}")
                return None
                
        return None

    def is_uk_location(self, location: str) -> bool:
        """Check if location is in the UK using patterns"""
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
        
        # If API is available, try geocoding
        if self.api_available:
            lat, lng, _ = self.geocode_location(location)
            if lat and lng:
                return (self.uk_bounds['south'] <= lat <= self.uk_bounds['north'] and 
                        self.uk_bounds['west'] <= lng <= self.uk_bounds['east'])
        
        # Default assumption for common UK terms
        return any(term in location_lower for term in ['high street', 'city centre', 'town centre'])

    def get_here_parking_data(self, lat: float, lng: float) -> List[Dict]:
        """Get detailed parking data from HERE.com API or demo data"""
        if not self.api_available:
            logger.info("Using demo parking data")
            # Return demo data with adjusted positions
            demo_data = []
            for spot in self.demo_parking_spots:
                spot_copy = spot.copy()
                spot_copy['position'] = {'lat': lat, 'lng': lng}
                demo_data.append(spot_copy)
            return demo_data
        
        try:
            # Search for parking using HERE Discover API
            params = {
                'at': f"{lat},{lng}",
                'q': 'parking',
                'limit': 20,
                'apiKey': self.api_key,
                'categories': '700-7600-0116,700-7600-0117,700-7600-0118'  # Parking categories
            }
            
            data = self.safe_api_request(self.base_url, params)
            if not data:
                logger.warning("API request failed, using demo data")
                return self.demo_parking_spots
            
            parking_spots = []
            for item in data.get('items', []):
                spot_data = self.extract_here_spot_data(item)
                if spot_data:
                    parking_spots.append(spot_data)
            
            return parking_spots if parking_spots else self.demo_parking_spots
            
        except Exception as e:
            logger.error(f"Error in get_here_parking_data: {e}")
            return self.demo_parking_spots

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
            logger.error(f"Error extracting HERE data: {e}")
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
        
        # Extract time
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
        
        # Extract duration
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
        try:
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
                
        except Exception as e:
            logger.error(f"Error in generate_contextual_response: {e}")
            return {
                'message': "I'm having a small technical hiccup! 🔧",
                'response': "Don't worry - I'm still here to help with your UK parking needs. Please try again!",
                'suggestions': [
                    "Try asking about parking in a UK city",
                    "Ask about UK parking rules",
                    "Ask about parking prices"
                ],
                'type': 'error_recovery',
                'status': 'partial'
            }

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
        """Handle UK parking location queries"""
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
        
        # Search for parking
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
            'response': "I can help you find parking spots across the UK, explain parking rules and regulations, and give you pricing information. I use real data combined with UK parking expertise! 🎯",
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
            'response': "I can help you with: finding parking spots across the UK, explaining parking rules and restrictions, providing pricing information, and giving location-specific advice!",
            'suggestions': [
                "Find parking in [UK location]",
                "Ask about parking rules and restrictions",
                "Get pricing information for UK cities"
            ],
            'type': 'general',
            'status': 'success'
        }

    def geocode_location(self, location_query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Convert location query to coordinates with UK preference"""
        if not self.api_available:
            # Return demo coordinates for common UK cities
            demo_coords = {
                'london': (51.5074, -0.1278, 'London, UK'),
                'birmingham': (52.4862, -1.8904, 'Birmingham, UK'),
                'manchester': (53.4808, -2.2426, 'Manchester, UK'),
                'leeds': (53.8008, -1.5491, 'Leeds, UK'),
                'liverpool': (53.4084, -2.9916, 'Liverpool, UK'),
                'bristol': (51.4545, -2.5879, 'Bristol, UK'),
                'sheffield': (53.3811, -1.4701, 'Sheffield, UK'),
                'glasgow': (55.8642, -4.2518, 'Glasgow, UK'),
                'edinburgh': (55.9533, -3.1883, 'Edinburgh, UK')
            }
            
            location_lower = location_query.lower()
            for city, coords in demo_coords.items():
                if city in location_lower:
                    return coords
            
            # Default to London for demo
            return demo_coords['london']
        
        params = {
            'q': location_query,
            'apiKey': self.api_key,
            'limit': 5,
            'in': f"bbox:{self.uk_bounds['west']},{self.uk_bounds['south']},{self.uk_bounds['east']},{self.uk_bounds['north']}"
        }

        try:
            data = self.safe_api_request(self.geocoding_url, params)
            
            if data and data.get('items'):
                # Prefer UK results
                for item in data['items']:
                    position = item['position']
                    if (self.uk_bounds['south'] <= position['lat'] <= self.uk_bounds['north'] and 
                        self.uk_bounds['west'] <= position['lng'] <= self.uk_bounds['east']):
                        address = item.get('address', {}).get('label', location_query)
                        return position['lat'], position['lng'], address
                
                # If no UK result found, return first result
                position = data['items'][0]['position']
                address = data['items'][0].get('address', {}).get('label', location_query)
                return position['lat'], position['lng'], address
            else:
                return None, None, None
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            return None, None, None

# Flask App Setup
app = Flask(__name__)
CORS(app)

# Initialize bot with error handling
try:
    bot = IntelligentParksyBot()
    logger.info("UK Parksy Bot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    bot = None

@app.route('/', methods=['GET'])
def home():
    """API home endpoint"""
    api_status = "active" if bot and bot.api_available else "demo mode"
    
    return jsonify({
        "message": "🇬🇧 UK Parksy Bot - Your British Parking Assistant!",
        "version": "4.1 - Enhanced Error Handling",
        "status": api_status,
        "coverage": "United Kingdom Only",
        "features": [
            "Real-time parking data (when API available)",
            "UK parking rules and regulations",
            "Accurate pricing information", 
            "Location-specific guidance",
            "Robust error handling",
            "Demo mode fallback"
        ],
        "data_sources": [
            "HERE.com Places API (when available)",
            "UK parking regulations database",
            "Local authority parking policies",
            "Demo data (fallback mode)"
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
    api_status = "available" if bot and bot.api_available else "demo mode"
    bot_status = "healthy" if bot else "error"
    
    return jsonify({
        "status": bot_status,
        "bot_status": "Ready to help with UK parking! 🇬🇧",
        "api_status": api_status,
        "timestamp": datetime.now().isoformat(),
        "version": "4.1",
        "here_api_configured": bool(os.getenv('HERE_API_KEY')),
        "coverage": "United Kingdom",
        "data_accuracy": "High - Real data + UK regulations (demo fallback available)"
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chat endpoint - UK parking specialist"""
    try:
        if not bot:
            return jsonify({
                "message": "I'm temporarily unavailable! 🔧",
                "response": "The bot service is currently initializing. Please try again in a moment.",
                "status": "error"
            }), 503

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
        response['api_mode'] = "live" if bot.api_available else "demo"
        
        return jsonify(response)

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return jsonify({
            "message": "Sorry, I've encountered a technical issue! 🔧",
            "response": "Don't worry - I'm still here to help with your UK parking needs. Please try again!",
            "error": "Internal server error",
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "message": "Endpoint not found! 🗺️",
        "response": "Try the /api/chat endpoint for parking assistance or / for API information.",
        "status": "error"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "message": "Internal server error! 🔧",
        "response": "Something went wrong on our end. Please try again.",
        "status": "error"
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print("🇬🇧 Starting UK Parksy Bot...")
    print("📍 Coverage: United Kingdom Only")
    print(f"🎯 API Mode: {'Live' if bot and bot.api_available else 'Demo'}")
    print("💬 Ready for accurate UK parking assistance!")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
